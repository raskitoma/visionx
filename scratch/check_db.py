import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

target_db_raw = os.getenv("TARGET_DB", "")
user_pass, host_port_db = target_db_raw.split('@')
user, pwd = user_pass.split(':')
host_port, db = host_port_db.split('/')
host, port = host_port.split(':')

try:
    conn = pymysql.connect(
        host=host,
        port=int(port),
        user=user,
        password=pwd,
        database=db,
        cursorclass=pymysql.cursors.DictCursor
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            print(cur.fetchone())
            
            cur.execute("SELECT SourceLine, LaneId, nDetected, SyncUp FROM vision_samples ORDER BY SyncUp DESC LIMIT 10")
            print("Recent samples:")
            for row in cur.fetchall():
                print(row)
except Exception as e:
    print(f"Error: {e}")
