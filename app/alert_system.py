import logging
import pytz
from datetime import datetime, timedelta
from sync_engine import get_target_connection

logger = logging.getLogger("alert_system")

class AlertHandler:
    """Interface for handling alerts (e.g., system log, database, webhooks, etc.)."""
    def handle_alert(self, line: str, run_id: int, product_id: str, timestamp: datetime, errors: list):
        pass

class LogAlertHandler(AlertHandler):
    """Triggers alerts by logging them into the system log."""
    def handle_alert(self, line: str, run_id: int, product_id: str, timestamp: datetime, errors: list):
        error_str = "; ".join(errors)
        logger.error(f"[ALERT] Line {line} - Run {run_id} - Product {product_id} has specs violations: {error_str}")

class DbAlertHandler(AlertHandler):
    """Triggers alerts by recording them in the vision_alert_history target DB table."""
    def __init__(self, conn):
        self.conn = conn
        
    def handle_alert(self, line: str, run_id: int, product_id: str, timestamp: datetime, errors: list):
        error_str = "; ".join(errors)
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO vision_alert_history (SourceLine, AlertTime, RunId, ProductId, Details)
                    VALUES (%s, %s, %s, %s, %s)
                """, (line, timestamp, run_id, product_id, error_str))
            self.conn.commit()
            logger.info(f"Saved alert history to DB for Line {line}, Run {run_id}")
        except Exception as e:
            logger.error(f"Failed to save alert to DB for Line {line}, Run {run_id}: {e}")

class SlackAlertHandler(AlertHandler):
    """Triggers alerts by posting a notification to a Slack webhook."""
    def __init__(self, webhook_url: str, mention_target: str = None, conn = None):
        self.webhook_url = webhook_url
        self.mention_target = mention_target
        self.conn = conn

    def handle_alert(self, line: str, run_id: int, product_id: str, timestamp: datetime, errors: list):
        if line == 'TEST_LINE' or (line and line.startswith('TEST')):
            logger.info(f"Skipping Slack notification for test line: {line}")
            return
        import urllib.request
        import json
        import re

        mention_str = ""
        if self.mention_target:
            target = self.mention_target.strip()
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

        formatted_time = timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')
        
        # Parse and highlight faulty values using regular expressions
        formatted_errors = []
        pattern = re.compile(r"([A-Za-z0-9_]+)\s*\(([^)]+)\)\s*(is (?:above|below))\s*([A-Za-z0-9_]+)\s*\(([^)]+)\)")
        for err in errors:
            match = pattern.match(err)
            if match:
                param, val, direction, limit_name, limit_val = match.groups()
                formatted_errors.append(f"• *{param}* ( ` {val} ` ) {direction} {limit_name} ({limit_val})")
            else:
                formatted_errors.append(f"• {err}")
        
        error_bullet_points = "\n".join(formatted_errors)

        message = f"⚠️ *VisionX Specs Violation Alert*\n"
        if mention_str:
            message += f"{mention_str}\n"
        message += (
            f"*Line:* {line}\n"
            f"*Product ID:* {product_id}\n"
            f"*Run ID:* {run_id}\n"
            f"*Time:* {formatted_time}\n"
            f"*Details:*\n{error_bullet_points}"
        )

        payload = {"text": message}
        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                status = response.status
                if status == 200 or status == 204:
                    logger.info(f"Successfully sent Slack notification for Line {line}, Run {run_id}")
                    if self.conn:
                        try:
                            with self.conn.cursor() as cur:
                                cur.execute("""
                                    UPDATE vision_alert_history 
                                    SET SlackSentTime = NOW() 
                                    WHERE SourceLine = %s AND RunId = %s
                                """, (line, run_id))
                            self.conn.commit()
                        except Exception as dbe:
                            logger.error(f"Failed to update SlackSentTime in DB: {dbe}")
                else:
                    logger.error(f"Slack webhook returned non-200 status: {status}")
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")


def check_run_limits(run: dict, product: dict) -> list:
    """Compares the run averages against the product specification limits."""
    errors = []
    
    # Extract actual averages
    d_major = run.get('DMajorAverage')
    d_minor = run.get('DMinorAverage')
    d_avg = run.get('DAvgAverage')
    
    # Extract product specification targets and limits
    elliptic = product.get('Elliptic')
    d1_target = product.get('D1Target')
    d2_target = product.get('D2Target')
    d1_min = product.get('D1Min')
    d1_max = product.get('D1Max')
    d2_min = product.get('D2Min')
    d2_max = product.get('D2Max')
    
    # 1. DAvg check (alert if DAvg is off)
    if d_avg is not None:
        d_avg_min = product.get('DAvgMin')
        d_avg_max = product.get('DAvgMax')
        
        # Fallback if DAvgMin/DAvgMax are not specified in product spec
        if d_avg_min is None:
            if elliptic:
                m1 = d1_min if d1_min is not None else d1_target
                m2 = d2_min if d2_min is not None else (d2_target if d2_target is not None else m1)
                if m1 is not None and m2 is not None:
                    d_avg_min = (m1 + m2) / 2.0
            else:
                d_avg_min = d1_min
                
        if d_avg_max is None:
            if elliptic:
                m1 = d1_max if d1_max is not None else d1_target
                m2 = d2_max if d2_max is not None else (d2_target if d2_target is not None else m1)
                if m1 is not None and m2 is not None:
                    d_avg_max = (m1 + m2) / 2.0
            else:
                d_avg_max = d1_max
                
        if d_avg_min is not None and d_avg < d_avg_min:
            errors.append(f"DAvgAverage ({d_avg:.3f}) is below DAvgMin ({d_avg_min:.3f})")
        if d_avg_max is not None and d_avg > d_avg_max:
            errors.append(f"DAvgAverage ({d_avg:.3f}) is above DAvgMax ({d_avg_max:.3f})")

    # 2. Ratio check (alert when ratio is off)
    if d_major is not None:
        # If DMinor is missing for circular products, default it to DMajor
        if d_minor is None and not elliptic:
            d_minor = d_major
            
        if d_minor is not None and d_major > 0:
            actual_ratio = d_minor / d_major
            
            # Determine expected limits for Major and Minor
            t_major_min = d1_min if d1_min is not None else d1_target
            t_major_max = d1_max if d1_max is not None else d1_target
            
            if elliptic:
                t_minor_min = d2_min if d2_min is not None else (d2_target if d2_target is not None else t_major_min)
                t_minor_max = d2_max if d2_max is not None else (d2_target if d2_target is not None else t_major_max)
            else:
                t_minor_min = t_major_min
                t_minor_max = t_major_max
                
            if t_major_max and t_major_min and t_minor_min is not None and t_minor_max is not None:
                ratio_min = t_minor_min / t_major_max
                ratio_max = t_minor_max / t_major_min
                
                if actual_ratio < ratio_min:
                    errors.append(f"ProductRatio ({actual_ratio:.3f}) is below expected limit ({ratio_min:.3f})")
                if actual_ratio > ratio_max:
                    errors.append(f"ProductRatio ({actual_ratio:.3f}) is above expected limit ({ratio_max:.3f})")

    return errors

def run_alert_check():
    """Runs the 30-minute alert verification cycle."""
    logger.info("Starting 30-minute alert verification cycle...")
    ny_tz = pytz.timezone('America/New_York')
    now_ny = datetime.now(ny_tz)
    cutoff_ny = now_ny - timedelta(minutes=30)
    
    # Target DB stores timezone-naive local datetimes
    cutoff_naive = cutoff_ny.replace(tzinfo=None)
    now_naive = now_ny.replace(tzinfo=None)
    
    conn = None
    try:
        conn = get_target_connection()
        if not conn:
            logger.error("Could not connect to target DB for alert checking.")
            return
            
        slack_handler = None
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) as cnt FROM information_schema.tables 
                    WHERE table_schema = DATABASE() AND table_name = 'vision_slack_settings'
                """)
                table_exists = cur.fetchone()
                if table_exists and table_exists['cnt'] > 0:
                    cur.execute("SELECT webhook_url, mention_target, is_enabled FROM vision_slack_settings WHERE id = 1")
                    settings = cur.fetchone()
                    if settings and settings['is_enabled'] and settings['webhook_url']:
                        slack_handler = SlackAlertHandler(settings['webhook_url'], settings['mention_target'], conn=conn)
        except Exception as se:
            logger.warning(f"Could not load Slack settings: {se}")

        handlers = [
            LogAlertHandler(),
            DbAlertHandler(conn)
        ]
        if slack_handler:
            handlers.append(slack_handler)
            logger.info("Slack alerts are enabled and handler is attached.")
        
        with conn.cursor() as cur:
            # Find active runs with activity (LastUpdate) in the last 30 minutes
            cur.execute("""
                SELECT * FROM vision_runs 
                WHERE EndTime IS NULL AND LastUpdate >= %s
            """, (cutoff_naive,))
            active_runs = cur.fetchall()
            
            if not active_runs:
                logger.info("No active or updated runs found in the last 30 minutes.")
                return
                
            logger.info(f"Analyzing {len(active_runs)} active/updated runs for parameter compliance...")
            
            for run in active_runs:
                line = run['SourceLine']
                run_id = run['RunId']
                product_id = run['ProductId']
                
                # Only check runs that have been active for at least 30 minutes
                # (exclude test lines from this check so tests can run immediately)
                run_start = run['StartTime']
                is_test = line == 'TEST_LINE' or (line and line.startswith('TEST'))
                if not is_test and run_start and (now_naive - run_start) < timedelta(minutes=30):
                    logger.info(f"Run {run_id} on Line {line} has been active for less than 30 minutes (started at {run_start}). Skipping alert check.")
                    continue
                
                # Check if an alert was already triggered for this run to avoid duplicates
                cur.execute("""
                    SELECT COUNT(*) as cnt FROM vision_alert_history 
                    WHERE SourceLine = %s AND RunId = %s
                """, (line, run_id))
                cnt_row = cur.fetchone()
                already_alerted = cnt_row['cnt'] > 0 if cnt_row else False
                
                if already_alerted:
                    logger.info(f"Alert already triggered for Line {line}, Run {run_id}. Skipping duplicate check.")
                    continue
                
                # Fetch product spec
                cur.execute("""
                    SELECT * FROM vision_product 
                    WHERE SourceLine = %s AND ProductId = %s
                """, (line, product_id))
                product = cur.fetchone()
                
                if not product:
                    logger.warning(f"Product specifications not found for Line {line}, Product {product_id}. Skipping validation.")
                    continue
                    
                # Fetch 30-minute average of samples for this run
                cur.execute("""
                    SELECT 
                        COUNT(*) as sample_count,
                        AVG(DMajorAverage) as DMajorAverage,
                        AVG(DMinorAverage) as DMinorAverage,
                        AVG(DAvgAverage) as DAvgAverage,
                        AVG(EFAverage) as EFAverage,
                        AVG(EDAverage) as EDAverage,
                        AVG(HAAverage) as HAAverage,
                        AVG(ShapeAverage) as ShapeAverage,
                        AVG(ToastAverage) as ToastAverage,
                        AVG(RawAverage) as RawAverage,
                        AVG(TransAverage) as TransAverage
                    FROM vision_samples
                    WHERE SourceLine = %s AND RunId = %s AND SampTime >= %s AND LaneId = '*'
                """, (line, run_id, cutoff_naive))
                avg_row = cur.fetchone()
                
                if avg_row and avg_row.get('sample_count', 0) > 0:
                    errors = check_run_limits(avg_row, product)
                else:
                    errors = []
                if errors:
                    # Alert trigger!
                    for handler in handlers:
                        try:
                            # Use NY timezone-aware time for the alert representation
                            handler.handle_alert(line, run_id, product_id, now_ny, errors)
                        except Exception as eh:
                            logger.error(f"Error executing alert handler {handler.__class__.__name__}: {eh}")
                            
        logger.info("Alert verification cycle completed.")
    except Exception as e:
        logger.error(f"Critical error during alert check cycle: {e}")
    finally:
        if conn:
            conn.close()
