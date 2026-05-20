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
from alert_system import run_alert_check
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
scheduler.add_job(run_alert_check, 'interval', minutes=30, max_instances=1, next_run_time=datetime.now())
def init_settings_table():
    if not TARGET:
        logging.error("No TARGET database configured. Skipping settings table initialization.")
        return
    try:
        conn = pymysql.connect(
            host=TARGET['host'],
            port=TARGET['port'],
            user=TARGET['user'],
            password=TARGET['password'],
            database=TARGET['database'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS `vision_slack_settings` (
                      `id` int(11) NOT NULL AUTO_INCREMENT,
                      `webhook_url` varchar(500) NOT NULL,
                      `mention_target` varchar(100) DEFAULT NULL,
                      `is_enabled` tinyint(1) NOT NULL DEFAULT '1',
                      `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
                      `updated_at` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                      PRIMARY KEY (`id`)
                    ) ENGINE=InnoDB DEFAULT CHARSET=latin1;
                """)
                cur.execute("SELECT COUNT(*) as count FROM vision_slack_settings")
                row = cur.fetchone()
                if row and row['count'] == 0:
                    cur.execute("""
                        INSERT INTO vision_slack_settings (id, webhook_url, mention_target, is_enabled)
                        VALUES (1, '', '', 0)
                    """)
                
                # Check and add SlackSentTime to vision_alert_history if missing
                try:
                    cur.execute("SHOW COLUMNS FROM `vision_alert_history` LIKE 'SlackSentTime'")
                    if not cur.fetchone():
                        logging.info("Adding SlackSentTime column to vision_alert_history...")
                        cur.execute("ALTER TABLE `vision_alert_history` ADD COLUMN `SlackSentTime` datetime DEFAULT NULL")
                except Exception as ex:
                    logging.error(f"Failed to verify/add SlackSentTime column: {ex}")
                    
            conn.commit()
            logging.info("vision_slack_settings table and vision_alert_history columns initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize settings table or verify columns: {e}")

@app.on_event("startup")
def start_scheduler():
    init_settings_table()
    scheduler.start()

@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()

from pydantic import BaseModel
from typing import Optional

class SlackSettingsSchema(BaseModel):
    webhook_url: str
    mention_target: Optional[str] = None
    is_enabled: bool

@app.get("/api/settings/slack")
def get_slack_settings():
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
                cur.execute("SELECT webhook_url, mention_target, is_enabled FROM vision_slack_settings WHERE id = 1")
                row = cur.fetchone()
                if not row:
                    return {"webhook_url": "", "mention_target": "", "is_enabled": False}
                return {
                    "webhook_url": row["webhook_url"],
                    "mention_target": row["mention_target"] or "",
                    "is_enabled": bool(row["is_enabled"])
                }
    except Exception as e:
        logging.error(f"Error fetching Slack settings: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/settings/slack")
def save_slack_settings(settings: SlackSettingsSchema):
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
                    INSERT INTO vision_slack_settings (id, webhook_url, mention_target, is_enabled)
                    VALUES (1, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        webhook_url = VALUES(webhook_url),
                        mention_target = VALUES(mention_target),
                        is_enabled = VALUES(is_enabled)
                """, (settings.webhook_url, settings.mention_target, 1 if settings.is_enabled else 0))
            conn.commit()
        return {"success": True, "message": "Slack settings saved successfully"}
    except Exception as e:
        logging.error(f"Error saving Slack settings: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

class SlackTestSchema(BaseModel):
    webhook_url: str
    mention_target: Optional[str] = None

@app.post("/api/settings/slack/test")
def test_slack_settings(payload: SlackTestSchema):
    if not payload.webhook_url:
        return JSONResponse({"error": "Webhook URL is required"}, status_code=400)
    
    import urllib.request
    import json
    
    mention_str = ""
    if payload.mention_target:
        target = payload.mention_target.strip()
        if target:
            if target.startswith('U') and len(target) >= 9:
                mention_str = f"<@{target}> "
            elif target in ['here', 'channel']:
                mention_str = f"<!{target}> "
            else:
                clean_target = target.lstrip('@#')
                if clean_target in ['here', 'channel']:
                    mention_str = f"<!{clean_target}> "
                elif clean_target.startswith('U') and len(clean_target) >= 9:
                    mention_str = f"<@{clean_target}> "
                else:
                    mention_str = f"@{clean_target} "

    message = "🧪 *VisionX Slack Test Alert*\n"
    if mention_str:
        message += f"{mention_str}\n"
    message += "This is a test notification confirming that your VisionX Slack integration is active and working correctly!"
    
    slack_payload = {"text": message}
    try:
        req = urllib.request.Request(
            payload.webhook_url,
            data=json.dumps(slack_payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.status
            if status == 200 or status == 204:
                return {"success": True, "message": "Test alert sent successfully"}
            else:
                return JSONResponse({"error": f"Slack returned status {status}"}, status_code=400)
    except Exception as e:
        logging.error(f"Slack test alert failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)



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
                now = datetime.now(ny_tz)
                cutoff = now - timedelta(minutes=30)
                cutoff_naive = cutoff.replace(tzinfo=None)

                cur.execute("""
                    SELECT 
                        SourceLine,
                        AVG(DMajorAverage) as DMajor,
                        AVG(DMinorAverage) as DMinor,
                        AVG(DAvgAverage) as DAvg,
                        AVG(EFAverage) as EF,
                        AVG(EDAverage) as ED,
                        AVG(HAAverage) as HA,
                        AVG(ShapeAverage) as Shape,
                        AVG(ToastAverage) as Toast,
                        AVG(RawAverage) as Raw,
                        AVG(TransAverage) as Trans
                    FROM vision_samples
                    WHERE SampTime >= %s AND LaneId = '*'
                    GROUP BY SourceLine
                """, (cutoff_naive,))
                avg_rows = cur.fetchall()
                avg_30m = {}
                for arow in avg_rows:
                    avg_30m[arow['SourceLine']] = {
                        'DMajor': arow['DMajor'],
                        'DMinor': arow['DMinor'],
                        'DAvg': arow['DAvg'],
                        'EF': arow['EF'],
                        'ED': arow['ED'],
                        'HA': arow['HA'],
                        'Shape': arow['Shape'],
                        'Toast': arow['Toast'] / 100.0 if arow['Toast'] is not None else None,
                        'Raw': arow['Raw'] / 100.0 if arow['Raw'] is not None else None,
                        'Trans': arow['Trans'] / 100.0 if arow['Trans'] is not None else None
                    }

        result = {}
        for row in rows:
            line = row['SourceLine']
            
            # Determine isRunning based on LastUpdate
            last_update = row['LastUpdate']
            if last_update:
                if last_update.tzinfo is None:
                    last_update = ny_tz.localize(last_update)
                diff_seconds = (now - last_update).total_seconds()
                row['isRunning'] = diff_seconds < (MINUTES_LAST_UPDATE * 60)
            else:
                row['isRunning'] = False

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
                'isRunning':    row.get('isRunning', False),
                'averages_30m': avg_30m.get(line, None),
            }
        return result
    except Exception as e:
        logging.error(f"Error fetching runs: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/products")
def get_products():
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
                cur.execute("SELECT * FROM vision_product ORDER BY SourceLine, ProductId")
                rows = cur.fetchall()

        ny_tz = pytz.timezone('America/New_York')
        result = {}
        for row in rows:
            line = row['SourceLine']
            if line not in result:
                result[line] = []

            def safe_localize(dt):
                if not dt: return None
                if dt.tzinfo is None:
                    return ny_tz.localize(dt).isoformat()
                return dt.isoformat()

            prod_entry = {
                'ProductId': row['ProductId'],
                'ProductDesc': row['ProductDesc'],
                'Elliptic': row['Elliptic'],
                'D1Min': row['D1Min'],
                'D1Target': row['D1Target'],
                'D1Max': row['D1Max'],
                'D2Min': row['D2Min'],
                'D2Target': row['D2Target'],
                'D2Max': row['D2Max'],
                'DAvgMin': row['DAvgMin'],
                'DAvgMax': row['DAvgMax'],
                'EFMax': row['EFMax'],
                'EFFlatDef': row['EFFlatDef'],
                'EDMax': row['EDMax'],
                'HAMax': row['HAMax'],
                'ShapeMax': row['ShapeMax'],
                'ToastMin': row['ToastMin'],
                'RawMax': row['RawMax'],
                'TransMax': row['TransMax'],
                'LastUpdate': safe_localize(row['LastUpdate']),
                'SyncUp': safe_localize(row['SyncUp'])
            }
            result[line].append(prod_entry)
        return result
    except Exception as e:
        logging.error(f"Error fetching products: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/alerts")
def get_alerts(limit: int = 50):
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
                    SELECT * FROM vision_alert_history 
                    ORDER BY AlertTime DESC 
                    LIMIT %s
                """, (limit,))
                rows = cur.fetchall()

        ny_tz = pytz.timezone('America/New_York')
        result = []
        for row in rows:
            def safe_localize(dt):
                if not dt: return None
                if dt.tzinfo is None:
                    return ny_tz.localize(dt).isoformat()
                return dt.isoformat()

            result.append({
                'id': row['id'],
                'SourceLine': row['SourceLine'],
                'AlertTime': safe_localize(row['AlertTime']),
                'RunId': row['RunId'],
                'ProductId': row['ProductId'],
                'Details': row['Details'],
                'SlackSentTime': safe_localize(row.get('SlackSentTime')),
                'created_at': safe_localize(row['created_at'])
            })
        return result
    except Exception as e:
        logging.error(f"Error fetching alerts: {e}")
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
