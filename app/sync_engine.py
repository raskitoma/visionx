import pymysql
import time
import logging
import pytz
from datetime import datetime, timedelta
import concurrent.futures
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from config import SOURCES, TARGET, INFLUX, RECORDS_LIMIT, VNC_PORT, VNC_PASSWORD, MINUTES_LAST_UPDATE

import os

log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, 'sync.log'))
    ]
)
logger = logging.getLogger(__name__)

sync_state = {
    "lines": {},
    "vnc_port": VNC_PORT,
    "vnc_password": VNC_PASSWORD,
    "minutes_last_update": MINUTES_LAST_UPDATE,
    "last_sync": None
}

def get_table_columns(conn, table_name):
    """Fetch column names for a given table in the target DB."""
    try:
        with conn.cursor() as cur:
            cur.execute(f"DESCRIBE `{table_name}`")
            columns = [row['Field'] for row in cur.fetchall()]
            return columns
    except Exception as e:
        logger.error(f"Error fetching columns for {table_name}: {e}")
        return []

def filter_columns(data_dict, allowed_cols):
    """Filter dictionary to only include keys present in allowed_cols."""
    return {k: v for k, v in data_dict.items() if k in allowed_cols}

def get_target_connection():
    if not TARGET:
        return None
    return pymysql.connect(
        host=TARGET['host'],
        port=TARGET['port'],
        user=TARGET['user'],
        password=TARGET['password'],
        database=TARGET['database'],
        cursorclass=pymysql.cursors.DictCursor,
        charset='latin1',
        connect_timeout=30,
        read_timeout=120
    )

def get_source_connection(src):
    return pymysql.connect(
        host=src['host'],
        port=src['port'],
        user=src['user'],
        password=src['password'],
        database=src['database'],
        cursorclass=pymysql.cursors.DictCursor,
        charset='latin1',
        connect_timeout=30,
        read_timeout=60
    )

def write_to_influx(data_points):
    if not INFLUX['token']: return
    try:
        with InfluxDBClient(url=INFLUX['url'], token=INFLUX['token'], org=INFLUX['org']) as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=INFLUX['bucket'], record=data_points)
    except Exception as e:
        logger.error(f"InfluxDB write error: {e}")

def get_corrected_datetime(host_dt, source_dt, is_legacy):
    """
    Unified time correction logic:
    - Legacy (!): Use Host Date. Compare time part only. If offset > 10m, use Host Time.
    - Newer: Use Source Date. Compare full datetime. If offset > 10m, use Host Time.
    """
    if not source_dt:
        return host_dt
    try:
        if is_legacy:
            # ALWAYS use Host Date.
            # Compare only the time part (ignoring date)
            h_time_only = host_dt.replace(year=2000, month=1, day=1, tzinfo=None)
            s_time_only = source_dt.replace(year=2000, month=1, day=1, tzinfo=None)
            diff_seconds = abs((h_time_only - s_time_only).total_seconds())
            
            if diff_seconds > 600: # 10 minutes
                # Time part is too far off. Use full Host DT.
                return host_dt
            else:
                # Time part is close. Use Host Date + Source Time.
                return host_dt.replace(
                    hour=source_dt.hour,
                    minute=source_dt.minute,
                    second=source_dt.second,
                    microsecond=source_dt.microsecond
                )
        else:
            # Newer system. Use Source Date.
            # Compare full datetime.
            diff_seconds = abs((host_dt.replace(tzinfo=None) - source_dt.replace(tzinfo=None)).total_seconds())
            
            if diff_seconds > 600: # 10 minutes
                # Full datetime is too far off. Move it to Host Time but keep Source Date.
                return source_dt.replace(
                    hour=host_dt.hour,
                    minute=host_dt.minute,
                    second=host_dt.second,
                    microsecond=host_dt.microsecond
                )
            else:
                # Trust Source fully (but ensure it has host_dt's timezone info for DB consistency)
                return source_dt.replace(tzinfo=host_dt.tzinfo)
    except Exception as e:
        logger.warning(f"Failed to combine datetime: {e}")
        return host_dt

def sync_source(src, target_cols, current_sync_time):
    line = src['line']
    host = src['host']
    is_legacy = src.get('override_time', False)
    start_time = time.time()
    logger.info(f"\033[96m-------==== Review {line} ({host}) =====---\033[0m")
    
    mysql_ok = "notok"
    ping_ok = False
    
    # Initialize state so the line appears in the API immediately
    if line not in sync_state['lines']:
        sync_state['lines'][line] = {
            "host": host,
            "status": "initializing",
            "last_sync": current_sync_time.isoformat(),
            "ping": False
        }

    tgt_conn = None
    src_conn = None
    created_count = 0
    updated_count = 0
    
    # Retry loop for Target DB initialization
    last_run_id = 0
    last_samp_no = 0
    target_ready = False
    
    for attempt in range(3):
        try:
            tgt_conn = get_target_connection()
            if not tgt_conn:
                raise Exception("Target connection returned None")
                
            with tgt_conn.cursor() as cur:
                # Fetch last synced info
                cur.execute("SELECT MAX(RunId) as max_run FROM vision_runs WHERE SourceLine = %s", (line,))
                row = cur.fetchone()
                last_run_id = row['max_run'] if row and row['max_run'] is not None else 0
                
                cur.execute("SELECT MAX(SampNo) as max_samp FROM vision_samples WHERE SourceLine = %s", (line,))
                row = cur.fetchone()
                last_samp_no = row['max_samp'] if row and row['max_samp'] is not None else 0
            
            target_ready = True
            break
        except Exception as e:
            if tgt_conn: tgt_conn.close()
            logger.warning(f"Target DB attempt {attempt+1} failed for {line}: {e}")
            time.sleep(1)

    if not target_ready:
        error_msg = f"Could not initialize target DB for {line} after 3 attempts"
        logger.error(error_msg)
        sync_state['lines'][line] = {
            "host": host,
            "status": "error",
            "error": error_msg,
            "last_sync": current_sync_time.isoformat(),
            "ping": False
        }
        return
    
    try:
        import subprocess
        ping_ok = True
        try:
            res = subprocess.run(['ping', '-c', '1', '-W', '5', host], capture_output=True)
            ping_ok = (res.returncode == 0)
        except Exception:
            ping_ok = False
            
        try:
            if not ping_ok:
                logger.warning(f"Host {host} unreachable via ping. Attempting connection anyway...")
                
            src_conn = get_source_connection(src)
            mysql_ok = "OK"
            with src_conn.cursor() as cur:
                # Sync runs
                cur.execute("SELECT * FROM runs WHERE RunId >= %s ORDER BY RunId ASC LIMIT %s", (last_run_id, RECORDS_LIMIT))
                runs_data = cur.fetchall()
                
                # Ensure we also get the ABSOLUTE LATEST run to keep the dashboard live
                cur.execute("SELECT MAX(RunId) as abs_max FROM runs")
                abs_max_row = cur.fetchone()
                if abs_max_row and abs_max_row['abs_max']:
                    abs_max_id = abs_max_row['abs_max']
                    if not any(r['RunId'] == abs_max_id for r in runs_data):
                        cur.execute("SELECT * FROM runs WHERE RunId = %s", (abs_max_id,))
                        latest_run_data = cur.fetchone()
                        if latest_run_data:
                            runs_data.append(latest_run_data)
                            logger.info(f"Added absolute latest run {abs_max_id} to sync for {line} (Live Priority)")

                influx_points = []
                if runs_data:
                    logger.info(f"Targeting {len(runs_data)} runs to sync for {line}...")
                    with tgt_conn.cursor() as tcur:
                        for rd in runs_data:
                            # Original source times
                            rd['origin_StartTime'] = rd.get('StartTime')
                            rd['origin_EndTime'] = rd.get('EndTime')
                            rd['origin_FirstTime'] = rd.get('FirstTime')
                            rd['origin_LastTime'] = rd.get('LastTime')

                            # Use the unified correction logic
                            rd['StartTime'] = get_corrected_datetime(current_sync_time, rd.get('origin_StartTime'), is_legacy)
                            if rd.get('EndTime'):
                                rd['EndTime'] = get_corrected_datetime(current_sync_time, rd.get('origin_EndTime'), is_legacy)
                            if rd.get('FirstTime'):
                                rd['FirstTime'] = get_corrected_datetime(current_sync_time, rd.get('origin_FirstTime'), is_legacy)
                            if rd.get('LastTime'):
                                rd['LastTime'] = get_corrected_datetime(current_sync_time, rd.get('origin_LastTime'), is_legacy)
                            
                            rd['SyncUp'] = current_sync_time
                            rd['LastUpdate'] = current_sync_time
                            
                            # Filter columns to match target schema
                            rd_filtered = filter_columns(rd, target_cols['runs'])
                            cols = ['SourceLine'] + list(rd_filtered.keys())
                            vals = [line] + list(rd_filtered.values())
                            placeholders = ", ".join(["%s"] * len(vals))
                            col_names = ", ".join([f"`{c}`" for c in cols])
                            
                            # LastUpdate logic - exclude metadata and heartbeat timestamps from change detection
                            exclude_runs = ['SyncUp', 'LastUpdate', 'created_at', 'StartTime', 'SourceLine', 'RunId', 'FirstTime', 'LastTime']
                            content_cols = [c for c in rd_filtered.keys() if c not in exclude_runs and not c.startswith('origin_')]
                            change_cond = " OR ".join([f"NOT (`{c}` <=> VALUES(`{c}`))" for c in content_cols]) if content_cols else "FALSE"
                            update_parts = [f"`LastUpdate` = IF({change_cond}, VALUES(`LastUpdate`), `LastUpdate`)"]
                            
                            for c in cols:
                                if c not in ['StartTime', 'created_at', 'LastUpdate']:
                                    update_parts.append(f"`{c}`=VALUES(`{c}`)")
                            update_clause = ", ".join(update_parts)
                            
                            q = f"INSERT INTO `vision_runs` ({col_names}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
                            try:
                                affected = tcur.execute(q, tuple(vals))
                                if affected == 1: created_count += 1
                                elif affected == 2: updated_count += 1
                            except Exception as ex:
                                logger.error(f"Error inserting run {rd.get('RunId')} for {line}: {ex}")

                            # Influx - always server time per request
                            p = Point("production_run") \
                                .tag("line", line) \
                                .tag("RunId", str(rd['RunId'])) \
                                .tag("ProductId", str(rd.get('ProductId', 'Unknown'))) \
                                .field("nDetected", int(rd.get('nDetected', 0) or 0)) \
                                .field("nPassed", int(rd.get('nPassed', 0) or 0)) \
                                .field("nMarginal", int(rd.get('nMarginal', 0) or 0)) \
                                .field("nRejected", int(rd.get('nRejected', 0) or 0))
                            influx_points.append(p)
                
                # Sync lanes
                cur.execute("SELECT * FROM lanes WHERE RunId >= %s ORDER BY RunId ASC, LaneId ASC LIMIT %s", (last_run_id, RECORDS_LIMIT * 5))
                lanes_data = cur.fetchall()
                if lanes_data:
                    logger.info(f"Targeting {len(lanes_data)} lanes to sync for {line}...")
                    with tgt_conn.cursor() as tcur:
                        for ld in lanes_data:
                            # Original source times
                            ld['origin_FirstTime'] = ld.get('FirstTime')
                            ld['origin_LastTime'] = ld.get('LastTime')

                            if ld.get('FirstTime'):
                                ld['FirstTime'] = get_corrected_datetime(current_sync_time, ld.get('origin_FirstTime'), is_legacy)
                            if ld.get('LastTime'):
                                ld['LastTime'] = get_corrected_datetime(current_sync_time, ld.get('origin_LastTime'), is_legacy)
                            
                            ld['SyncUp'] = current_sync_time
                            ld['LastUpdate'] = current_sync_time
                            
                            ld_filtered = filter_columns(ld, target_cols['lanes'])
                            cols = ['SourceLine'] + list(ld_filtered.keys())
                            vals = [line] + list(ld_filtered.values())
                            placeholders = ", ".join(["%s"] * len(vals))
                            col_names = ", ".join([f"`{c}`" for c in cols])
                            
                            exclude_lanes = ['SyncUp', 'LastUpdate', 'created_at', 'SourceLine', 'RunId', 'LaneId', 'FirstTime', 'LastTime']
                            content_cols = [c for c in ld_filtered.keys() if c not in exclude_lanes and not c.startswith('origin_')]
                            change_cond = " OR ".join([f"NOT (`{c}` <=> VALUES(`{c}`))" for c in content_cols]) if content_cols else "FALSE"
                            update_parts = [f"`LastUpdate` = IF({change_cond}, VALUES(`LastUpdate`), `LastUpdate`)"]
                            
                            for c in cols:
                                if c not in ['created_at', 'LastUpdate']:
                                    update_parts.append(f"`{c}`=VALUES(`{c}`)")
                            update_clause = ", ".join(update_parts)
                            
                            q = f"INSERT INTO `vision_lanes` ({col_names}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
                            try:
                                affected = tcur.execute(q, tuple(vals))
                                if affected == 1: created_count += 1
                                elif affected == 2: updated_count += 1
                            except Exception as ex:
                                pass
                                
                # Sync samples - Incremental
                cur.execute("""
                    SELECT * FROM samples 
                    WHERE (RunId = %s AND SampNo > %s) OR (RunId > %s) 
                    ORDER BY RunId ASC, SampNo ASC 
                    LIMIT %s
                """, (last_run_id, last_samp_no, last_run_id, RECORDS_LIMIT * 10))
                samples_data = cur.fetchall()
                if samples_data:
                    logger.info(f"Targeting {len(samples_data)} samples to sync for {line}...")
                    with tgt_conn.cursor() as tcur:
                        for sd in samples_data:
                            sd['origin_SampTime'] = sd.get('SampTime')
                            sd['SampTime'] = get_corrected_datetime(current_sync_time, sd.get('origin_SampTime'), is_legacy)
                            
                            sd['SyncUp'] = current_sync_time
                            sd['LastUpdate'] = current_sync_time
                            
                            sd_filtered = filter_columns(sd, target_cols['samples'])
                            cols = ['SourceLine'] + list(sd_filtered.keys())
                            vals = [line] + list(sd_filtered.values())
                            placeholders = ", ".join(["%s"] * len(vals))
                            col_names = ", ".join([f"`{c}`" for c in cols])
                            
                            exclude_samples = ['SyncUp', 'LastUpdate', 'created_at', 'SampTime', 'SourceLine', 'RunId', 'LaneId', 'SampNo']
                            content_cols = [c for c in sd_filtered.keys() if c not in exclude_samples and not c.startswith('origin_')]
                            change_cond = " OR ".join([f"NOT (`{c}` <=> VALUES(`{c}`))" for c in content_cols]) if content_cols else "FALSE"
                            update_parts = [f"`LastUpdate` = IF({change_cond}, VALUES(`LastUpdate`), `LastUpdate`)"]
                            
                            for c in cols:
                                if c not in ['created_at', 'LastUpdate']:
                                    update_parts.append(f"`{c}`=VALUES(`{c}`)")
                            update_clause = ", ".join(update_parts)

                            q = f"INSERT INTO `vision_samples` ({col_names}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
                            try:
                                affected = tcur.execute(q, tuple(vals))
                                if affected == 1: created_count += 1
                                elif affected == 2: updated_count += 1
                            except Exception as ex:
                                pass
                                
                            p = Point("production_sample") \
                                .tag("line", line) \
                                .tag("lane", sd.get('LaneId', '*')) \
                                .field("nDetected", int(sd.get('nDetected', 0) or 0)) \
                                .field("nPassed", int(sd.get('nPassed', 0) or 0)) \
                                .field("nMarginal", int(sd.get('nMarginal', 0) or 0)) \
                                .field("nRejected", int(sd.get('nRejected', 0) or 0))
                            
                            influx_points.append(p)
                
                tgt_conn.commit()
                
                if influx_points:
                    write_to_influx(influx_points)

                sync_state['lines'][line] = {
                    "host": host,
                    "last_run_id": runs_data[-1]['RunId'] if runs_data else last_run_id,
                    "last_samp_no": samples_data[-1]['SampNo'] if samples_data else last_samp_no,
                    "status": "online",
                    "last_sync": current_sync_time.isoformat(),
                    "error": None,
                    "ping": ping_ok
                }

        except Exception as e:
            logger.error(f"Error syncing {line}: {e}")
            sync_state['lines'][line] = {
                "host": host,
                "status": "error",
                "error": str(e),
                "last_sync": current_sync_time.isoformat(),
                "ping": ping_ok
            }
        finally:
            duration = time.time() - start_time
            # Always try to save results to vision_history if target DB is available
            if tgt_conn:
                try:
                    with tgt_conn.cursor() as tcur:
                        tcur.execute("""
                            SELECT RunId, LastTime, nDetected, nPassed, nMarginal, nRejected 
                            FROM vision_runs 
                            WHERE SourceLine = %s 
                            ORDER BY RunId DESC, LastTime DESC 
                            LIMIT 1
                        """, (line,))
                        latest_run = tcur.fetchone()
                        if latest_run:
                            tcur.execute("""
                                INSERT INTO vision_history 
                                (SourceLine, RunId, Kind, Date_Run, Date_Source, nDetected, nPassed, nMarginal, nRejected, Process_Time)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (
                                line, 
                                latest_run['RunId'], 
                                "legacy" if is_legacy else "newer", 
                                current_sync_time, 
                                latest_run['LastTime'], 
                                latest_run['nDetected'], 
                                latest_run['nPassed'], 
                                latest_run['nMarginal'], 
                                latest_run['nRejected'], 
                                duration
                            ))
                        tgt_conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to record persistent history for {line}: {e}")

            ping_str = "ok" if ping_ok else "notok"
            changes_str = "YES" if (created_count + updated_count > 0) else "NO"
            summary = f"{line} - Ping {ping_str} - Mysql {mysql_ok} - changes detected: {changes_str} - {updated_count} records updated, {created_count} records created. Duration: {duration:.2f}s"
            logger.info(f"\033[92m{summary}\033[0m")
            
            if src_conn:
                src_conn.close()
            if tgt_conn:
                tgt_conn.close()
    except Exception as e:
        logger.error(f"Critical error in sync_source for {line}: {e}")

def run_sync():
    logger.info("Starting sync cycle...")
    ny_tz = pytz.timezone('America/New_York')
    current_sync_time = datetime.now(ny_tz)
    
    # Pre-fetch target columns once
    tgt_conn = None
    try:
        tgt_conn = get_target_connection()
        if not tgt_conn:
            logger.error("Could not connect to target DB for schema pre-fetch")
            return
        target_cols = {
            'runs':    get_table_columns(tgt_conn, 'vision_runs'),
            'lanes':   get_table_columns(tgt_conn, 'vision_lanes'),
            'samples': get_table_columns(tgt_conn, 'vision_samples')
        }
        tgt_conn.close()
    except Exception as e:
        logger.error(f"Error during schema pre-fetch: {e}")
        return

    # Run source syncs in parallel (Max 3)
    sorted_sources = sorted(SOURCES, key=lambda x: x['line'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        for src in sorted_sources:
            futures.append(executor.submit(sync_source, src, target_cols, current_sync_time))
            time.sleep(1) # Stagger start to avoid concurrent DB connection spikes
        concurrent.futures.wait(futures)
    
    sync_state['last_sync'] = current_sync_time.isoformat()
    logger.info("Sync cycle completed.")
