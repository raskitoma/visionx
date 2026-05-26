import os
import sys
import pymysql
from influxdb_client import InfluxDBClient

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- 1. Verify MariaDB ---
target_db_raw = os.getenv("TARGET_DB", "")
if target_db_raw:
    try:
        user_pass, host_port_db = target_db_raw.split('@')
        user, pwd = user_pass.split(':')
        host_port, db = host_port_db.split('/')
        host, port = host_port.split(':')
        config = {
            "user": user,
            "password": pwd,
            "host": host,
            "port": int(port),
            "database": db
        }
        conn = pymysql.connect(
            host=config['host'],
            port=config['port'],
            user=config['user'],
            password=config['password'],
            database=config['database'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        try:
            with conn.cursor() as cur:
                print("\n--- MariaDB: vision_runs ---")
                cur.execute("""
                    SELECT SourceLine, RunId, ProductId, TargetDMajorMin, TargetDMajorMax, TargetDMinorMin, TargetDMinorMax, TargetProductRatio 
                    FROM vision_runs 
                    WHERE TargetDMajorMin IS NOT NULL 
                    LIMIT 2
                """)
                for r in cur.fetchall():
                    print(f"Run: Line={r['SourceLine']} | RunId={r['RunId']} | ProductId={r['ProductId']}")
                    print(f"  Limits: Major={r['TargetDMajorMin']}-{r['TargetDMajorMax']} | Minor={r['TargetDMinorMin']}-{r['TargetDMinorMax']}")
                    print(f"  Ratio: {r['TargetProductRatio']}")

                print("\n--- MariaDB: vision_samples ---")
                cur.execute("""
                    SELECT SourceLine, RunId, SampNo, TargetDMajorMin, TargetDMajorMax, TargetDMinorMin, TargetDMinorMax, TargetProductRatio 
                    FROM vision_samples 
                    WHERE TargetDMajorMin IS NOT NULL 
                    LIMIT 2
                """)
                for r in cur.fetchall():
                    print(f"Sample: Line={r['SourceLine']} | RunId={r['RunId']} | SampNo={r['SampNo']}")
                    print(f"  Limits: Major={r['TargetDMajorMin']}-{r['TargetDMajorMax']} | Minor={r['TargetDMinorMin']}-{r['TargetDMinorMax']}")
                    print(f"  Ratio: {r['TargetProductRatio']}")
        finally:
            conn.close()
    except Exception as e:
        print(f"MariaDB query error: {e}")

# --- 2. Verify InfluxDB ---
url = os.getenv("INFLUX_HOST", "http://influxdb:8086")
token = os.getenv("INFLUX_TOKEN", "")
org = os.getenv("INFLUX_ORG", "")
bucket = os.getenv("INFLUX_BUCKET", "visionx")

def check_influx(measurement):
    print(f"\n--- InfluxDB: {measurement} ---")
    query = f'''
    from(bucket: "{bucket}")
      |> range(start: -30m)
      |> filter(fn: (r) => r["_measurement"] == "{measurement}")
      |> filter(fn: (r) => r["_field"] =~ /TargetD(Major|Minor)(Min|Max)/ or r["_field"] == "TargetProductRatio")
    '''
    try:
        with InfluxDBClient(url=url, token=token, org=org, timeout=10000) as client:
            query_api = client.query_api()
            tables = query_api.query(query)
            
            records = {}
            for table in tables:
                for record in table.records:
                    time_key = record.get_time()
                    line = record.values.get('line')
                    run_id = record.values.get('RunId')
                    lane = record.values.get('lane', '*')
                    
                    key = (time_key, line, run_id, lane)
                    if key not in records:
                        records[key] = {}
                    records[key][record.get_field()] = record.get_value()
            
            if not records:
                print(f"No recent target limits or ratio fields found in InfluxDB for '{measurement}'.")
            else:
                for i, (key, fields) in enumerate(list(records.items())[:2]):
                    time_key, line, run_id, lane = key
                    print(f"Point {i+1}: Time={time_key} | Line={line} | RunId={run_id} | Lane={lane}")
                    print(f"  Fields: {fields}")
    except Exception as e:
        print(f"InfluxDB query error for {measurement}: {e}")

check_influx("production_run")
check_influx("production_sample")
