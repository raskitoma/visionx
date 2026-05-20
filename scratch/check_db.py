import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

target_db_raw = os.getenv("TARGET_DB", "")
user_pass, host_port_db = target_db_raw.split('@')
user, pwd = user_pass.split(':')
host_port, db = host_port_db.split('/')
host, port = host_port.split(':')

# Print target info
print(f"Target DB: {host}:{port}/{db}")

# Parse source DBs
source_dbs_raw = os.getenv("SOURCE_DBS", "")
sources = source_dbs_raw.split(",")

for src in sources:
    if not src:
        continue
    # Format: [!]user:pass@host:port/dbname|LineName
    is_legacy = src.startswith("!")
    conn_str = src[1:] if is_legacy else src
    parts = conn_str.split("|")
    line_name = parts[1]
    conn_info = parts[0]
    
    s_user_pass, s_host_port_db = conn_info.split("@")
    s_user, s_pwd = s_user_pass.split(":")
    s_host_port, s_db = s_host_port_db.split("/")
    s_host, s_port = s_host_port.split(":")
    
    print(f"\n--- Source Line: {line_name} ({s_host}:{s_port}/{s_db}) ---")
    try:
        s_conn = pymysql.connect(
            host=s_host,
            port=int(s_port),
            user=s_user,
            password=s_pwd,
            database=s_db,
            cursorclass=pymysql.cursors.DictCursor,
            charset='latin1'
        )
        with s_conn:
            with s_conn.cursor() as cur:
                # Latest runs in source
                cur.execute("SELECT RunId, ProductId, ToastAverage, RawAverage, TransAverage FROM runs ORDER BY RunId DESC LIMIT 3")
                runs = cur.fetchall()
                print("Latest runs in SOURCE:")
                for r in runs:
                    print(r)
                    run_id = r['RunId']
                    cur.execute("SELECT COUNT(*), MAX(SampNo), AVG(ToastAverage), AVG(RawAverage), AVG(TransAverage) FROM samples WHERE RunId = %s", (run_id,))
                    samp_stats = cur.fetchone()
                    print(f"  Samples in SOURCE for Run {run_id}: {samp_stats}")
                    cur.execute("SELECT ToastAverage, RawAverage, TransAverage FROM samples WHERE RunId = %s LIMIT 3", (run_id,))
                    print(f"  Sample values in SOURCE: {cur.fetchall()}")
    except Exception as e:
        print(f"  Error querying source: {e}")

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
            print("\n--- Target DB runs and sample counts ---")
            cur.execute("SELECT SourceLine, COUNT(*) FROM vision_samples GROUP BY SourceLine")
            print("Total samples in target DB per line:")
            for row in cur.fetchall():
                print(row)
            
            for l in ['L01', 'L05']:
                cur.execute("SELECT MAX(SampNo) as max_overall FROM vision_samples WHERE SourceLine = %s", (l,))
                max_o = cur.fetchone()['max_overall']
                cur.execute("SELECT MAX(RunId) as max_run FROM vision_runs WHERE SourceLine = %s", (l,))
                max_r = cur.fetchone()['max_run']
                cur.execute("SELECT COUNT(*) as cnt_run, MAX(SampNo) as max_run_samp FROM vision_samples WHERE SourceLine = %s AND RunId = %s", (l, max_r))
                run_stats = cur.fetchone()
                print(f"Line {l}: MaxRun={max_r}, MaxOverallSampNo={max_o}, StatsForMaxRun={run_stats}")
            
            cur.execute("SELECT * FROM vision_product WHERE ProductId = '10in'")
            print("\nProduct specs for 10in:")
            for row in cur.fetchall():
                print(row)
                
            cur.execute("SELECT * FROM vision_runs WHERE SourceLine = 'L01' AND RunId = 9543")
            print("\nRun 9543 in target DB:")
            for row in cur.fetchall():
                print(row)
            
            cur.execute("SELECT SourceLine, RunId, StartTime, LastTime, LastUpdate FROM vision_runs ORDER BY LastUpdate DESC LIMIT 5")
            for r in cur.fetchall():
                print(r)
                cur.execute("SELECT COUNT(*), MAX(SampNo) FROM vision_samples WHERE SourceLine = %s AND RunId = %s", (r['SourceLine'], r['RunId']))
                print(f"  Samples in TARGET: {cur.fetchone()}")
except Exception as e:
    print(f"Error: {e}")
