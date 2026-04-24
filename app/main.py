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

from datetime import datetime, timedelta
import pytz
import subprocess
from config import SOURCES, MINUTES_LAST_UPDATE

def run_ping():
    for src in SOURCES:
        line = src['line']
        host = src['host']
        try:
            res = subprocess.run(['ping', '-c', '1', '-W', '5', host], capture_output=True)
            ping_ok = (res.returncode == 0)
        except Exception:
            ping_ok = False
            
        if line not in sync_state['lines']:
            sync_state['lines'][line] = {}
        sync_state['lines'][line]['ping'] = ping_ok

scheduler = BackgroundScheduler()
scheduler.add_job(run_sync, 'interval', minutes=1, max_instances=1, next_run_time=datetime.now())
scheduler.add_job(run_ping, 'interval', seconds=10, max_instances=1, next_run_time=datetime.now())
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
            connect_timeout=30,
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

                ny_tz = pytz.timezone('America/New_York')
                threshold_time = datetime.now(ny_tz) - timedelta(minutes=MINUTES_LAST_UPDATE)
                cur.execute("""
                    SELECT 
                        SourceLine,
                        SUM(
                            (max_det > min_det) OR 
                            (max_pas > min_pas) OR 
                            (max_mar > min_mar) OR 
                            (max_rej > min_rej)
                        ) > 0 as is_running
                    FROM (
                        SELECT 
                            SourceLine, 
                            RunId, 
                            MAX(nDetected) as max_det, MIN(nDetected) as min_det,
                            MAX(nPassed) as max_pas, MIN(nPassed) as min_pas,
                            MAX(nMarginal) as max_mar, MIN(nMarginal) as min_mar,
                            MAX(nRejected) as max_rej, MIN(nRejected) as min_rej
                        FROM vision_history
                        WHERE Date_Run >= %s
                        GROUP BY SourceLine, RunId
                    ) t
                    GROUP BY SourceLine
                """, (threshold_time,))
                status_rows = cur.fetchall()
                status_map = {r['SourceLine']: bool(r['is_running']) for r in status_rows}

        result = {}
        for row in rows:
            line = row['SourceLine']
            row['isRunning'] = status_map.get(line, False)

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
        conn = pymysql.connect(
            host=TARGET['host'],
            port=TARGET['port'],
            user=TARGET['user'],
            password=TARGET['password'],
            database=TARGET['database'],
            cursorclass=pymysql.cursors.DictCursor,
            charset='latin1',
            connect_timeout=30,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        SourceLine,
                        SUM(max_detected - min_detected) as nDetected,
                        SUM(max_passed - min_passed) as nPassed,
                        SUM(max_marginal - min_marginal) as nMarginal,
                        SUM(max_rejected - min_rejected) as nRejected
                    FROM (
                        SELECT 
                            SourceLine, 
                            RunId, 
                            MAX(nDetected) as max_detected, MIN(nDetected) as min_detected,
                            MAX(nPassed) as max_passed, MIN(nPassed) as min_passed,
                            MAX(nMarginal) as max_marginal, MIN(nMarginal) as min_marginal,
                            MAX(nRejected) as max_rejected, MIN(nRejected) as min_rejected
                        FROM vision_history
                        WHERE Date_Run >= NOW() - INTERVAL 1 HOUR
                        GROUP BY SourceLine, RunId
                    ) t
                    GROUP BY SourceLine
                """)
                rows = cur.fetchall()
        
        result = {}
        for row in rows:
            line = row['SourceLine']
            result[line] = {
                'nDetected': int(row['nDetected'] or 0),
                'nPassed': int(row['nPassed'] or 0),
                'nMarginal': int(row['nMarginal'] or 0),
                'nRejected': int(row['nRejected'] or 0)
            }
        
        return result
    except Exception as e:
        logging.error(f"Error fetching hour stats from InfluxDB: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.websocket("/ws/vnc/{host}/{port}")
async def vnc_proxy(websocket: WebSocket, host: str, port: int):
    # Translate line name to IP if needed
    actual_host = host
    for src in SOURCES:
        if src['line'] == host:
            actual_host = src['host']
            logging.info(f"VNC Proxy: Translating line name '{host}' to IP '{actual_host}'")
            break

    await websocket.accept()
    logging.info(f"VNC Proxy: WebSocket accepted for {host}:{port} (Actual: {actual_host})")
    try:
        # Connect to VNC server (TCP) with retries
        max_retries = 3
        reader, writer = None, None
        
        for attempt in range(1, max_retries + 1):
            logging.info(f"VNC Proxy: Connecting to TCP {actual_host}:{port} (Attempt {attempt}/{max_retries})...")
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(actual_host, port), timeout=15.0)
                logging.info(f"VNC Proxy: TCP Connection established to {actual_host}:{port}")
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
