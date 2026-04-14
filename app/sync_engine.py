import pymysql
import logging
import pytz
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from config import SOURCES, TARGET, INFLUX, RECORDS_LIMIT

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
        charset='latin1'
    )

def get_source_connection(src):
    return pymysql.connect(
        host=src['host'],
        port=src['port'],
        user=src['user'],
        password=src['password'],
        database=src['database'],
        cursorclass=pymysql.cursors.DictCursor,
        charset='latin1'
    )

def write_to_influx(data_points):
    if not INFLUX['token']: return
    try:
        with InfluxDBClient(url=INFLUX['url'], token=INFLUX['token'], org=INFLUX['org']) as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=INFLUX['bucket'], record=data_points)
    except Exception as e:
        logger.error(f"InfluxDB write error: {e}")

def run_sync():
    logger.info("Starting sync cycle...")
    ny_tz = pytz.timezone('America/New_York')
    current_sync_time = datetime.now(ny_tz)
    
    tgt_conn = None
    try:
        tgt_conn = get_target_connection()
    except Exception as e:
        logger.error(f"Could not connect to target DB: {e}")
        return

    if not tgt_conn: return

    # Pre-fetch target columns to avoid schema mismatch errors (e.g. L02 extra columns)
    target_cols = {
        'runs':    get_table_columns(tgt_conn, 'vision_runs'),
        'lanes':   get_table_columns(tgt_conn, 'vision_lanes'),
        'samples': get_table_columns(tgt_conn, 'vision_samples')
    }

    for src in SOURCES:
        line = src['line']
        logger.info(f"Syncing source {line} at {src['host']}")
        
        try:
            with tgt_conn.cursor() as cur:
                cur.execute("SELECT MAX(RunId) as max_run FROM vision_runs WHERE SourceLine = %s", (line,))
                row = cur.fetchone()
                last_run_id = row['max_run'] if row and row['max_run'] is not None else 0
                
                cur.execute("SELECT MAX(SampNo) as max_samp FROM vision_samples WHERE SourceLine = %s", (line,))
                row = cur.fetchone()
                last_samp_no = row['max_samp'] if row and row['max_samp'] is not None else 0
        except Exception as e:
            logger.error(f"Error querying target DB for {line}: {e}")
            continue

        src_conn = None
        try:
            src_conn = get_source_connection(src)
            with src_conn.cursor() as cur:
                is_first_sync = (last_run_id == 0)
                if is_first_sync:
                    cur.execute("SELECT MAX(RunId) as m FROM runs")
                    mr = cur.fetchone()
                    if mr and mr['m']:
                        last_run_id = max(0, mr['m'] - RECORDS_LIMIT)
                        
                influx_points = []
                # Sync runs
                if is_first_sync:
                    cur.execute("SELECT * FROM runs WHERE RunId >= %s ORDER BY RunId ASC LIMIT %s", (last_run_id, RECORDS_LIMIT))
                else:
                    cur.execute("SELECT * FROM runs WHERE RunId >= %s ORDER BY RunId ASC", (last_run_id,))
                
                runs_data = cur.fetchall()
                if runs_data:
                    logger.info(f"Targeting {len(runs_data)} runs to sync for {line}...")
                    with tgt_conn.cursor() as tcur:
                        for rd in runs_data:
                            # Original source times
                            rd['origin_StartTime'] = rd.get('StartTime')
                            rd['origin_EndTime'] = rd.get('EndTime')
                            rd['origin_FirstTime'] = rd.get('FirstTime')
                            rd['origin_LastTime'] = rd.get('LastTime')

                            # Determine which times to use for main columns
                            if src.get('override_time'):
                                rd['StartTime'] = current_sync_time
                                if rd.get('EndTime'): rd['EndTime'] = current_sync_time
                                if rd.get('FirstTime'): rd['FirstTime'] = current_sync_time
                                if rd.get('LastTime'): rd['LastTime'] = current_sync_time
                            
                            rd['SyncUp'] = current_sync_time
                            
                            # Filter columns to match target schema
                            rd_filtered = filter_columns(rd, target_cols['runs'])
                            cols = ['SourceLine'] + list(rd_filtered.keys())
                            vals = [line] + list(rd_filtered.values())
                            placeholders = ", ".join(["%s"] * len(vals))
                            col_names = ", ".join([f"`{c}`" for c in cols])
                            
                            # ON DUPLICATE KEY UPDATE: exclude StartTime and created_at
                            update_parts = []
                            for c in cols:
                                if c not in ['StartTime', 'created_at']:
                                    update_parts.append(f"`{c}`=VALUES(`{c}`)")
                            update_clause = ", ".join(update_parts)
                            
                            q = f"INSERT INTO `vision_runs` ({col_names}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
                            try:
                                tcur.execute(q, tuple(vals))
                            except Exception as ex:
                                logger.error(f"Error inserting run {rd.get('RunId')}: {ex}")

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
                cur.execute("SELECT * FROM lanes WHERE RunId >= %s ORDER BY RunId ASC, LaneId ASC", (last_run_id,))
                lanes_data = cur.fetchall()
                if lanes_data:
                    logger.info(f"Targeting {len(lanes_data)} lanes to sync for {line}...")
                    with tgt_conn.cursor() as tcur:
                        for ld in lanes_data:
                            # Original source times
                            ld['origin_FirstTime'] = ld.get('FirstTime')
                            ld['origin_LastTime'] = ld.get('LastTime')

                            # Determine which times to use for main columns
                            if src.get('override_time'):
                                if ld.get('FirstTime'): ld['FirstTime'] = current_sync_time
                                if ld.get('LastTime'): ld['LastTime'] = current_sync_time
                            
                            ld['SyncUp'] = current_sync_time
                            
                            # Filter columns to match target schema
                            ld_filtered = filter_columns(ld, target_cols['lanes'])
                            cols = ['SourceLine'] + list(ld_filtered.keys())
                            vals = [line] + list(ld_filtered.values())
                            placeholders = ", ".join(["%s"] * len(vals))
                            col_names = ", ".join([f"`{c}`" for c in cols])
                            
                            # ON DUPLICATE KEY UPDATE: exclude created_at
                            update_parts = [f"`{c}`=VALUES(`{c}`)" for c in cols if c != 'created_at']
                            update_clause = ", ".join(update_parts)
                            
                            q = f"INSERT INTO `vision_lanes` ({col_names}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
                            try:
                                tcur.execute(q, tuple(vals))
                            except Exception as ex:
                                pass
                                
                # Sync samples
                cur.execute("SELECT * FROM samples WHERE RunId >= %s ORDER BY RunId ASC, SampNo ASC", (last_run_id,))
                samples_data = cur.fetchall()
                if samples_data:
                    logger.info(f"Targeting {len(samples_data)} samples to sync for {line}...")
                    with tgt_conn.cursor() as tcur:
                        for sd in samples_data:
                            # Original source times
                            sd['origin_SampTime'] = sd.get('SampTime')

                            # Determine which times to use for main columns
                            if src.get('override_time'):
                                sd['SampTime'] = current_sync_time
                            
                            sd['SyncUp'] = current_sync_time
                            
                            # Filter columns to match target schema
                            sd_filtered = filter_columns(sd, target_cols['samples'])
                            cols = ['SourceLine'] + list(sd_filtered.keys())
                            vals = [line] + list(sd_filtered.values())
                            placeholders = ", ".join(["%s"] * len(vals))
                            col_names = ", ".join([f"`{c}`" for c in cols])
                            
                            # ON DUPLICATE KEY UPDATE: exclude created_at
                            update_parts = [f"`{c}`=VALUES(`{c}`)" for c in cols if c != 'created_at']
                            update_clause = ", ".join(update_parts)

                            q = f"INSERT INTO `vision_samples` ({col_names}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
                            try:
                                tcur.execute(q, tuple(vals))
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
                    "last_run_id": runs_data[-1]['RunId'] if runs_data else last_run_id,
                    "last_samp_no": samples_data[-1]['SampNo'] if samples_data else last_samp_no,
                    "status": "online",
                    "last_sync": current_sync_time.isoformat(),
                    "error": None
                }

        except Exception as e:
            logger.error(f"Error syncing {line}: {e}")
            sync_state['lines'][line] = {
                "status": "error",
                "error": str(e),
                "last_sync": current_sync_time.isoformat()
            }
        finally:
            if src_conn:
                src_conn.close()

    if tgt_conn:
        tgt_conn.close()
    
    sync_state['last_sync'] = current_sync_time.isoformat()
    logger.info("Sync cycle completed.")
