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

def check_run_limits(run: dict, product: dict) -> list:
    """Compares the run averages against the product specification limits."""
    errors = []
    
    # 1. D1 / DMajor limits
    d_major = run.get('DMajorAverage')
    if d_major is not None:
        d1_min = product.get('D1Min')
        d1_max = product.get('D1Max')
        if d1_min is not None and d_major < d1_min:
            errors.append(f"DMajorAverage ({d_major:.3f}) is below D1Min ({d1_min:.3f})")
        if d1_max is not None and d_major > d1_max:
            errors.append(f"DMajorAverage ({d_major:.3f}) is above D1Max ({d1_max:.3f})")

    # 2. D2 / DMinor limits (only if elliptic is true)
    elliptic = product.get('Elliptic')
    if elliptic:
        d_minor = run.get('DMinorAverage')
        if d_minor is not None:
            d2_min = product.get('D2Min')
            d2_max = product.get('D2Max')
            if d2_min is not None and d_minor < d2_min:
                errors.append(f"DMinorAverage ({d_minor:.3f}) is below D2Min ({d2_min:.3f})")
            if d2_max is not None and d_minor > d2_max:
                errors.append(f"DMinorAverage ({d_minor:.3f}) is above D2Max ({d2_max:.3f})")

    # 3. DAvg limits
    d_avg = run.get('DAvgAverage')
    if d_avg is not None:
        d_avg_min = product.get('DAvgMin')
        d_avg_max = product.get('DAvgMax')
        if d_avg_min is not None and d_avg < d_avg_min:
            errors.append(f"DAvgAverage ({d_avg:.3f}) is below DAvgMin ({d_avg_min:.3f})")
        if d_avg_max is not None and d_avg > d_avg_max:
            errors.append(f"DAvgAverage ({d_avg:.3f}) is above DAvgMax ({d_avg_max:.3f})")

    # 4. EFMax limit
    ef_avg = run.get('EFAverage')
    if ef_avg is not None:
        ef_max = product.get('EFMax')
        if ef_max is not None and ef_avg > ef_max:
            errors.append(f"EFAverage ({ef_avg:.3f}) is above EFMax ({ef_max})")

    # 5. EDMax limit
    ed_avg = run.get('EDAverage')
    if ed_avg is not None:
        ed_max = product.get('EDMax')
        if ed_max is not None and ed_avg > ed_max:
            errors.append(f"EDAverage ({ed_avg:.3f}) is above EDMax ({ed_max})")

    # 6. HAMax limit
    ha_avg = run.get('HAAverage')
    if ha_avg is not None:
        ha_max = product.get('HAMax')
        if ha_max is not None and ha_avg > ha_max:
            errors.append(f"HAAverage ({ha_avg:.3f}) is above HAMax ({ha_max:.3f})")

    # 7. ShapeMax limit
    shape_avg = run.get('ShapeAverage')
    if shape_avg is not None:
        shape_max = product.get('ShapeMax')
        if shape_max is not None and shape_avg > shape_max:
            errors.append(f"ShapeAverage ({shape_avg:.3f}) is above ShapeMax ({shape_max:.3f})")

    # 8. ToastMin limit
    toast_avg = run.get('ToastAverage')
    if toast_avg is not None:
        toast_avg_pct = toast_avg / 100.0
        toast_min = product.get('ToastMin')
        if toast_min is not None and toast_avg_pct < toast_min:
            errors.append(f"ToastAverage ({toast_avg_pct:.3f}%) is below ToastMin ({toast_min}%)")

    # 9. RawMax limit
    raw_avg = run.get('RawAverage')
    if raw_avg is not None:
        raw_avg_pct = raw_avg / 100.0
        raw_max = product.get('RawMax')
        if raw_max is not None and raw_avg_pct > raw_max:
            errors.append(f"RawAverage ({raw_avg_pct:.3f}%) is above RawMax ({raw_max}%)")

    # 10. TransMax limit
    trans_avg = run.get('TransAverage')
    if trans_avg is not None:
        trans_avg_pct = trans_avg / 100.0
        trans_max = product.get('TransMax')
        if trans_max is not None and trans_avg_pct > trans_max:
            errors.append(f"TransAverage ({trans_avg_pct:.3f}%) is above TransMax ({trans_max}%)")

    return errors

def run_alert_check():
    """Runs the 30-minute alert verification cycle."""
    logger.info("Starting 30-minute alert verification cycle...")
    ny_tz = pytz.timezone('America/New_York')
    now_ny = datetime.now(ny_tz)
    cutoff_ny = now_ny - timedelta(minutes=30)
    
    # Target DB stores timezone-naive local datetimes
    cutoff_naive = cutoff_ny.replace(tzinfo=None)
    
    conn = None
    try:
        conn = get_target_connection()
        if not conn:
            logger.error("Could not connect to target DB for alert checking.")
            return
            
        handlers = [
            LogAlertHandler(),
            DbAlertHandler(conn)
        ]
        
        with conn.cursor() as cur:
            # Find runs with activity (LastUpdate) in the last 30 minutes
            cur.execute("""
                SELECT * FROM vision_runs 
                WHERE LastUpdate >= %s
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
                
                # Fetch product spec
                cur.execute("""
                    SELECT * FROM vision_product 
                    WHERE SourceLine = %s AND ProductId = %s
                """, (line, product_id))
                product = cur.fetchone()
                
                if not product:
                    logger.warning(f"Product specifications not found for Line {line}, Product {product_id}. Skipping validation.")
                    continue
                    
                errors = check_run_limits(run, product)
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
