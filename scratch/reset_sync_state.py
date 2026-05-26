import os
import sys
import pymysql
from dotenv import load_dotenv

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

target_db_raw = os.getenv("TARGET_DB", "")
if not target_db_raw:
    print("Error: TARGET_DB env variable not configured")
    sys.exit(1)

# Parse target DB URL: user:password@host:port/database
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

print(f"Connecting to target database at {config['host']}...")
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
        for line in ['L04', 'L05']:
            # Get max RunId and max SampNo
            cur.execute("SELECT MAX(RunId) as max_run FROM vision_runs WHERE SourceLine = %s", (line,))
            max_run = cur.fetchone()['max_run']
            if max_run is None:
                continue
                
            cur.execute("SELECT MAX(SampNo) as max_samp FROM vision_samples WHERE SourceLine = %s AND RunId = %s", (line, max_run))
            max_samp = cur.fetchone()['max_samp']
            if max_samp is None:
                continue
                
            print(f"For Line {line}, RunId {max_run}, max SampNo is {max_samp}.")
            
            # Delete last 5 samples to force re-sync
            delete_limit = max_samp - 5
            cur.execute("DELETE FROM vision_samples WHERE SourceLine = %s AND RunId = %s AND SampNo > %s", (line, max_run, delete_limit))
            print(f"Deleted samples with SampNo > {delete_limit} for line {line}, run {max_run}")
            
    conn.commit()
    print("Reset completed successfully! Ready for sync to pull them back.")
except Exception as e:
    print(f"Error resetting sync state: {e}")
    conn.rollback()
finally:
    conn.close()
