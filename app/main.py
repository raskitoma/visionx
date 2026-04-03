from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
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
                        r.WidthAverage
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
            result[line] = {
                'RunId':        row['RunId'],
                'StartTime':    ny_tz.localize(row['StartTime']).isoformat() if row['StartTime'] else None,
                'EndTime':      ny_tz.localize(row['EndTime']).isoformat()   if row['EndTime']   else None,
                'FirstTime':    ny_tz.localize(row['FirstTime']).isoformat() if row['FirstTime'] else None,
                'LastTime':     ny_tz.localize(row['LastTime']).isoformat()  if row['LastTime']  else None,
                'ProductId':    row['ProductId'],
                'nDetected':    row['nDetected'],
                'nPassed':      row['nPassed'],
                'nMarginal':    row['nMarginal'],
                'nRejected':    row['nRejected'],
                'WidthAverage': row['WidthAverage'],
            }
        return result
    except Exception as e:
        logging.error(f"Error fetching runs: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

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
