from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
import os
import logging
import pymysql
from sync_engine import run_sync, sync_state
from config import TARGET

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
                # Calculate production deltas for each lane in the last minute
                # looking back 5 minutes to find the previous reference sample.
                cur.execute("""
                    SELECT 
                        SourceLine,
                        SUM(GREATEST(0, nDetected_delta)) as nDetected,
                        SUM(GREATEST(0, nPassed_delta)) as nPassed,
                        SUM(GREATEST(0, nMarginal_delta)) as nMarginal,
                        SUM(GREATEST(0, nRejected_delta)) as nRejected
                    FROM (
                        SELECT 
                            SourceLine,
                            SyncUp,
                            nDetected - COALESCE(LAG(nDetected) OVER (PARTITION BY SourceLine, LaneId ORDER BY SyncUp), nDetected) as nDetected_delta,
                            nPassed - COALESCE(LAG(nPassed) OVER (PARTITION BY SourceLine, LaneId ORDER BY SyncUp), nPassed) as nPassed_delta,
                            nMarginal - COALESCE(LAG(nMarginal) OVER (PARTITION BY SourceLine, LaneId ORDER BY SyncUp), nMarginal) as nMarginal_delta,
                            nRejected - COALESCE(LAG(nRejected) OVER (PARTITION BY SourceLine, LaneId ORDER BY SyncUp), nRejected) as nRejected_delta
                        FROM vision_samples
                        WHERE SyncUp >= NOW() - INTERVAL 5 MINUTE
                    ) t
                    WHERE SyncUp >= NOW() - INTERVAL 1 MINUTE
                    GROUP BY SourceLine
                """)
                rows = cur.fetchall()
        
        result = {}
        for row in rows:
            result[row['SourceLine']] = {
                'nDetected': int(row['nDetected'] or 0),
                'nPassed':   int(row['nPassed'] or 0),
                'nMarginal': int(row['nMarginal'] or 0),
                'nRejected': int(row['nRejected'] or 0),
            }
        return result
    except Exception as e:
        logging.error(f"Error fetching minute stats: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.websocket("/ws/vnc/{host}/{port}")
async def vnc_proxy(websocket: WebSocket, host: str, port: int):
    await websocket.accept()
    try:
        # Connect to VNC server (TCP)
        # Using a small timeout to avoid hanging
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5.0)
        
        async def forward_ws_to_tcp():
            try:
                while True:
                    data = await websocket.receive_bytes()
                    writer.write(data)
                    await writer.drain()
            except Exception:
                pass
            finally:
                if not writer.is_closing():
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except:
                        pass

        async def forward_tcp_to_ws():
            try:
                while True:
                    data = await reader.read(8192) # Increased buffer for better performance
                    if not data:
                        break
                    await websocket.send_bytes(data)
            except Exception:
                pass
            finally:
                try:
                    await websocket.close()
                except:
                    pass

        # Run both directions concurrently
        await asyncio.gather(forward_ws_to_tcp(), forward_tcp_to_ws())
        
    except Exception as e:
        logging.error(f"VNC Proxy Connection Error to {host}:{port}: {e}")
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
