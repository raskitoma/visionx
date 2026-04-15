from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
import os
import logging
import socket
import pymysql
from sync_engine import run_sync, sync_state
from config import TARGET, INFLUX
from influxdb_client import InfluxDBClient

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="VisionX Sync Tool")

from datetime import datetime
import pytz
scheduler = BackgroundScheduler()
scheduler.add_job(run_sync, 'interval', minutes=1, max_instances=1, next_run_time=datetime.now())

@app.on_event("startup")
def start_scheduler():
    scheduler.start()

@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()

@app.get("/api/status")
def get_status():
    ny_tz = pytz.timezone('America/New_York')
    # Force inclusion of timezone offset
    return {
        **sync_state,
        "serverTime": datetime.now(ny_tz).isoformat()
    }


@app.get("/api/runs")
def get_runs():
    if not TARGET:
        return JSONResponse({"error": "No target DB configured"}, status_code=503)
    try:
        conn = pymysql.connect(
            host=TARGET['host'],
            port=TARGET['port'],
            user=TARGET['user'],
            password=TARGET['password'],
            database=TARGET['database'],
            cursorclass=pymysql.cursors.DictCursor,
            charset='latin1',
            connect_timeout=5,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        r.SourceLine,
                        r.RunId,
                        r.StartTime,
                        r.EndTime,
                        r.FirstTime,
                        r.LastTime,
                        r.ProductId,
                        r.nDetected,
                        r.nPassed,
                        r.nMarginal,
                        r.nRejected,
                        r.WidthAverage,
                        r.LastUpdate
                    FROM vision_runs r
                    INNER JOIN (
                        SELECT SourceLine, MAX(RunId) AS MaxRunId
                        FROM vision_runs
                        GROUP BY SourceLine
                    ) latest ON r.SourceLine = latest.SourceLine AND r.RunId = latest.MaxRunId
                    ORDER BY r.SourceLine
                """)
                rows = cur.fetchall()
        result = {}
        ny_tz = pytz.timezone('America/New_York')
        for row in rows:
            line = row['SourceLine']
            def safe_localize(dt):
                if not dt: return None
                if dt.tzinfo is None:
                    return ny_tz.localize(dt).isoformat()
                return dt.isoformat()

            result[line] = {
                'RunId':        row['RunId'],
                'StartTime':    safe_localize(row['StartTime']),
                'EndTime':      safe_localize(row['EndTime']),
                'FirstTime':    safe_localize(row['FirstTime']),
                'LastTime':     safe_localize(row['LastTime']),
                'ProductId':    row['ProductId'],
                'nDetected':    row['nDetected'],
                'nPassed':      row['nPassed'],
                'nMarginal':    row['nMarginal'],
                'nRejected':    row['nRejected'],
                'WidthAverage': row['WidthAverage'],
                'LastUpdate':   safe_localize(row['LastUpdate']),
            }
        return result
    except Exception as e:
        logging.error(f"Error fetching runs: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/minute_stats")
def get_minute_stats():
    """
    Returns production statistics for the last hour (60 minutes).
    Fetches data from InfluxDB production_run measurement.
    """
    if not INFLUX['token']:
        return JSONResponse({"error": "InfluxDB not configured"}, status_code=503)
    
    try:
        query = f'''
        from(bucket: "{INFLUX['bucket']}")
          |> range(start: -60m)
          |> filter(fn: (r) => r["_measurement"] == "production_run")
          |> filter(fn: (r) => r["_field"] == "nDetected" or r["_field"] == "nPassed" or r["_field"] == "nMarginal" or r["_field"] == "nRejected")
          |> group(columns: ["line", "_field"])
          |> difference()
          |> filter(fn: (r) => r._value >= 0)
          |> sum()
        '''
        
        result = {}
        with InfluxDBClient(url=INFLUX['url'], token=INFLUX['token'], org=INFLUX['org']) as client:
            query_api = client.query_api()
            tables = query_api.query(query=query)
            
            for table in tables:
                for record in table.records:
                    line = record.values.get("line")
                    field = record.get_field()
                    value = record.get_value()
                    
                    if line not in result:
                        result[line] = {
                            'nDetected': 0,
                            'nPassed': 0,
                            'nMarginal': 0,
                            'nRejected': 0
                        }
                    result[line][field] = int(value or 0)
        
        return result
    except Exception as e:
        logging.error(f"Error fetching hour stats from InfluxDB: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.websocket("/ws/vnc/{host}/{port}")
async def vnc_proxy(websocket: WebSocket, host: str, port: int):
    await websocket.accept()
    logging.info(f"VNC Proxy: WebSocket accepted for {host}:{port}")
    try:
        # Connect to VNC server (TCP) with retries
        max_retries = 3
        reader, writer = None, None
        
        for attempt in range(1, max_retries + 1):
            logging.info(f"VNC Proxy: Connecting to TCP {host}:{port} (Attempt {attempt}/{max_retries})...")
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=15.0)
                logging.info(f"VNC Proxy: TCP Connection established to {host}:{port}")
                break
            except (asyncio.TimeoutError, socket.timeout):
                logging.warning(f"VNC Proxy: Connection timeout on attempt {attempt}")
                if attempt == max_retries:
                    raise
            except ConnectionRefusedError:
                logging.error(f"VNC Proxy: Connection refused by {host}:{port}")
                raise
            except Exception as e:
                logging.error(f"VNC Proxy: Unexpected error on attempt {attempt}: {type(e).__name__}: {e}")
                if attempt == max_retries:
                    raise
                await asyncio.sleep(1)

        if not reader or not writer:
            raise Exception("Failed to establish TCP connection after retries")
        
        ws_to_tcp_bytes = 0
        tcp_to_ws_bytes = 0

        async def forward_ws_to_tcp():
            nonlocal ws_to_tcp_bytes
            try:
                while True:
                    data = await websocket.receive_bytes()
                    ws_to_tcp_bytes += len(data)
                    writer.write(data)
                    await writer.drain()
            except Exception as e:
                logging.debug(f"VNC Proxy: WS -> TCP closed ({type(e).__name__})")
            finally:
                if not writer.is_closing():
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except:
                        pass

        async def forward_tcp_to_ws():
            nonlocal tcp_to_ws_bytes
            try:
                while True:
                    data = await reader.read(16384) # Increased buffer
                    if not data:
                        logging.info(f"VNC Proxy: TCP {host}:{port} closed by peer")
                        break
                    tcp_to_ws_bytes += len(data)
                    await websocket.send_bytes(data)
            except Exception as e:
                logging.debug(f"VNC Proxy: TCP -> WS closed ({type(e).__name__})")
            finally:
                logging.info(f"VNC Proxy: Session summary for {host}:{port} - Sent: {tcp_to_ws_bytes} bytes, Received: {ws_to_tcp_bytes} bytes")
                try:
                    await websocket.close()
                except:
                    pass

        # Run both directions concurrently
        await asyncio.gather(forward_ws_to_tcp(), forward_tcp_to_ws())
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}" if str(e) else type(e).__name__
        logging.error(f"VNC Proxy Final Failure to {host}:{port} - {error_msg}")
        try:
            await websocket.close(code=1006)
        except:
            pass


# ── Static File Serving ───────────────────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")

# If we are in the root directory, maybe static is there
if not os.path.isdir(static_dir):
    static_dir = os.path.join(os.getcwd(), "static")

if os.path.isdir(static_dir):
    # Mount subdirectories (assets, etc) but NOT the root
    # because we'll use a catch-all for the root/HTML.
    assets_dir = os.path.join(static_dir, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # Serve other top-level static files (favicon, etc)
    @app.get("/{file_name:path}")
    async def serve_static(file_name: str):
        # Allow API routes to pass through
        if file_name.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
            
        file_path = os.path.join(static_dir, file_name)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
            
        # Default to index.html for SPA routing
        return FileResponse(os.path.join(static_dir, "index.html"))

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(static_dir, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
