import os
from dotenv import load_dotenv

load_dotenv()

def parse_source_dbs(source_dbs_raw):
    # Format: user:pass@host:port/dbname|LineName,...
    dbs = []
    if not source_dbs_raw:
        return dbs
    parts = source_dbs_raw.split(',')
    for part in parts:
        try:
            override_time = False
            if part.startswith('!'):
                override_time = True
                part = part[1:]
            
            db_conn, line = part.split('|')
            user_pass, host_port_db = db_conn.split('@')
            user, pwd = user_pass.split(':')
            host_port, database = host_port_db.split('/')
            host, port = host_port.split(':')

            dbs.append({
                "user": user,
                "password": pwd,
                "host": host,
                "port": int(port),
                "database": database,
                "line": line,
                "override_time": override_time
            })
        except Exception as e:
            print(f"Error parsing source db config {part}: {e}")
    return dbs

def parse_target_db(target_db_raw):
    # Format: user:password@target-db:3306/target_db
    if not target_db_raw:
        return None
    try:
        user_pass, host_port_db = target_db_raw.split('@')
        user, pwd = user_pass.split(':')
        host_port, db = host_port_db.split('/')
        host, port = host_port.split(':')
        return {
            "user": user,
            "password": pwd,
            "host": host,
            "port": int(port),
            "database": db
        }
    except Exception as e:
        print(f"Error parsing target db config: {e}")
        return None

SOURCE_DBS_RAW = os.getenv("SOURCE_DBS", "")
TARGET_DB_RAW = os.getenv("TARGET_DB", "")
RECORDS_LIMIT = int(os.getenv("RECORDS_LIMIT", "100"))

SOURCES = parse_source_dbs(SOURCE_DBS_RAW)
TARGET = parse_target_db(TARGET_DB_RAW)

INFLUX = {
    "url": os.getenv("INFLUX_HOST", "http://influxdb:8086"),
    "token": os.getenv("INFLUX_TOKEN", ""),
    "org": os.getenv("INFLUX_ORG", ""),
    "bucket": os.getenv("INFLUX_BUCKET", "")
}

VNC_PORT = os.getenv("VNC_PORT", "5900")
VNC_PASSWORD = os.getenv("VNC_PASSWORD", "1043")
MINUTES_LAST_UPDATE = int(os.getenv("MINUTES_LAST_UPDATE", "10"))
