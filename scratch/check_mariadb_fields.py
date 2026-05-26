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
        # Check vision_runs
        print("\n--- Checking vision_runs table ---")
        cur.execute("""
            SELECT SourceLine, RunId, ProductId, TargetDMajor, TargetDMinor, TargetDAvg 
            FROM vision_runs 
            WHERE TargetDMajor IS NOT NULL 
            LIMIT 5
        """)
        rows = cur.fetchall()
        if not rows:
            print("No records found in vision_runs with non-null TargetDMajor/DMinor/DAvg columns.")
        else:
            for r in rows:
                print(f"Run: Line={r['SourceLine']} | RunId={r['RunId']} | ProductId={r['ProductId']} | TargetDMajor={r['TargetDMajor']} | TargetDMinor={r['TargetDMinor']} | TargetDAvg={r['TargetDAvg']}")

        # Check vision_samples
        print("\n--- Checking vision_samples table ---")
        cur.execute("""
            SELECT SourceLine, RunId, SampNo, TargetDMajor, TargetDMinor, TargetDAvg 
            FROM vision_samples 
            WHERE TargetDMajor IS NOT NULL 
            LIMIT 5
        """)
        rows = cur.fetchall()
        if not rows:
            print("No records found in vision_samples with non-null TargetDMajor/DMinor/DAvg columns.")
        else:
            for r in rows:
                print(f"Sample: Line={r['SourceLine']} | RunId={r['RunId']} | SampNo={r['SampNo']} | TargetDMajor={r['TargetDMajor']} | TargetDMinor={r['TargetDMinor']} | TargetDAvg={r['TargetDAvg']}")

finally:
    conn.close()
