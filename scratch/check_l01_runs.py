import pymysql
import os
from dotenv import load_dotenv
import pytz
from datetime import datetime, timedelta

load_dotenv()

target_db_raw = os.getenv("TARGET_DB", "")
user_pass, host_port_db = target_db_raw.split('@')
user, pwd = user_pass.split(':')
host_port, db = host_port_db.split('/')
host, port = host_port.split(':')

print(f"Target DB: {host}:{port}/{db}")

conn = pymysql.connect(
    host=host,
    port=int(port),
    user=user,
    password=pwd,
    database=db,
    cursorclass=pymysql.cursors.DictCursor
)

try:
    with conn:
        with conn.cursor() as cur:
            # Get active runs for L01
            cur.execute("SELECT * FROM vision_runs WHERE SourceLine = 'L01' ORDER BY RunId DESC LIMIT 5")
            runs = cur.fetchall()
            print("\n--- Recent Runs on L01 ---")
            for r in runs:
                print(f"RunId: {r['RunId']}, ProductId: {r['ProductId']}, LastUpdate: {r['LastUpdate']}")
                
                # Fetch 30-minute sample stats for this run
                ny_tz = pytz.timezone('America/New_York')
                now_ny = datetime.now(ny_tz)
                cutoff_naive = (now_ny - timedelta(minutes=30)).replace(tzinfo=None)
                
                cur.execute("""
                    SELECT 
                        COUNT(*) as cnt,
                        MIN(SampTime) as min_time,
                        MAX(SampTime) as max_time,
                        AVG(EFAverage) as avg_ef
                    FROM vision_samples
                    WHERE SourceLine = 'L01' AND RunId = %s AND LaneId = '*'
                """, (r['RunId'],))
                stats_all = cur.fetchone()
                
                cur.execute("""
                    SELECT 
                        COUNT(*) as cnt,
                        MIN(SampTime) as min_time,
                        MAX(SampTime) as max_time,
                        AVG(EFAverage) as avg_ef
                    FROM vision_samples
                    WHERE SourceLine = 'L01' AND RunId = %s AND SampTime >= %s AND LaneId = '*'
                """, (r['RunId'], cutoff_naive))
                stats_30m = cur.fetchone()
                
                print(f"  All samples: count={stats_all['cnt']}, avg_ef={stats_all['avg_ef']}, range=[{stats_all['min_time']} to {stats_all['max_time']}]")
                print(f"  30m samples (cutoff={cutoff_naive}): count={stats_30m['cnt']}, avg_ef={stats_30m['avg_ef']}, range=[{stats_30m['min_time']} to {stats_30m['max_time']}]")
                
                # Retrieve last 5 samples
                cur.execute("""
                    SELECT SampNo, SampTime, EFAverage 
                    FROM vision_samples 
                    WHERE SourceLine = 'L01' AND RunId = %s AND LaneId = '*'
                    ORDER BY SampTime DESC LIMIT 5
                """, (r['RunId'],))
                samples = cur.fetchall()
                print("  Last 5 samples:")
                for s in samples:
                    print(f"    SampNo: {s['SampNo']}, SampTime: {s['SampTime']}, EFAverage: {s['EFAverage']}")
                    
            # Let's inspect the alert history
            cur.execute("SELECT * FROM vision_alert_history WHERE SourceLine = 'L01' ORDER BY AlertTime DESC LIMIT 5")
            print("\n--- Recent Alerts on L01 ---")
            for alert in cur.fetchall():
                print(alert)
                
except Exception as e:
    print(f"Error: {e}")
