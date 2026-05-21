import pymysql
import os
import pytz
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
target_db_raw = os.getenv("TARGET_DB", "")
user_pass, host_port_db = target_db_raw.split('@')
user, pwd = user_pass.split(':')
host_port, db = host_port_db.split('/')
host, port = host_port.split(':')

conn = pymysql.connect(
    host=host,
    port=int(port),
    user=user,
    password=pwd,
    database=db,
    cursorclass=pymysql.cursors.DictCursor
)

ny_tz = pytz.timezone('America/New_York')
now_ny = datetime.now(ny_tz)

with conn:
    with conn.cursor() as cur:
        # Delete any existing recent alerts for L01
        cur.execute("DELETE FROM vision_alert_history WHERE SourceLine = 'L01' AND RunId = 9547")
        
        # Insert a fake alert for L01 run 9547
        cur.execute("""
            INSERT INTO vision_alert_history (SourceLine, AlertTime, RunId, ProductId, Details)
            VALUES (%s, %s, %s, %s, %s)
        """, ('L01', now_ny, 9547, '10in', 'DMajorAverage (9.500) is below D1Min (10.000); ToastAverage (12.000%) is below ToastMin (15%)'))
    conn.commit()

print("Inserted test alert for L01, Run 9547")
