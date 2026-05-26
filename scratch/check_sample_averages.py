import os
import sys
import pymysql

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

target_db_raw = os.getenv("TARGET_DB", "")
if not target_db_raw:
    print("Error: TARGET_DB env variable not configured")
    sys.exit(1)

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
except Exception as e:
    print(f"Error parsing TARGET_DB: {e}")
    sys.exit(1)

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
        print("\n--- Checking vision_samples table actuals ---")
        cur.execute("""
            SELECT SourceLine, RunId, SampNo, DMajorAverage, DMinorAverage, DAvgAverage 
            FROM vision_samples 
            WHERE DMajorAverage IS NOT NULL AND DMajorAverage > 0
            LIMIT 10
        """)
        for r in cur.fetchall():
            print(f"Sample: Line={r['SourceLine']} | RunId={r['RunId']} | SampNo={r['SampNo']}")
            print(f"  Averages: DMajor={r['DMajorAverage']} | DMinor={r['DMinorAverage']} | DAvg={r['DAvgAverage']}")
finally:
    conn.close()
