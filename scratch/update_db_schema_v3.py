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
        # Alter vision_runs
        print("Checking/altering vision_runs table...")
        cur.execute("SHOW COLUMNS FROM `vision_runs` LIKE 'origin_StartTime'")
        if cur.fetchone():
            print("origin_StartTime column already exists in vision_runs.")
        else:
            print("Adding origin_StartTime/EndTime/FirstTime/LastTime columns to vision_runs...")
            cur.execute("""
                ALTER TABLE `vision_runs`
                ADD COLUMN `origin_StartTime` datetime DEFAULT NULL COMMENT 'Raw source StartTime, before clock correction' AFTER `LastTime`,
                ADD COLUMN `origin_EndTime` datetime DEFAULT NULL COMMENT 'Raw source EndTime, before clock correction' AFTER `origin_StartTime`,
                ADD COLUMN `origin_FirstTime` datetime DEFAULT NULL COMMENT 'Raw source FirstTime, before clock correction' AFTER `origin_EndTime`,
                ADD COLUMN `origin_LastTime` datetime DEFAULT NULL COMMENT 'Raw source LastTime, before clock correction' AFTER `origin_FirstTime`
            """)
            print("vision_runs table updated successfully.")

        # Alter vision_lanes
        print("Checking/altering vision_lanes table...")
        cur.execute("SHOW COLUMNS FROM `vision_lanes` LIKE 'origin_FirstTime'")
        if cur.fetchone():
            print("origin_FirstTime column already exists in vision_lanes.")
        else:
            print("Adding origin_FirstTime/LastTime columns to vision_lanes...")
            cur.execute("""
                ALTER TABLE `vision_lanes`
                ADD COLUMN `origin_FirstTime` datetime DEFAULT NULL COMMENT 'Raw source FirstTime, before clock correction' AFTER `LastTime`,
                ADD COLUMN `origin_LastTime` datetime DEFAULT NULL COMMENT 'Raw source LastTime, before clock correction' AFTER `origin_FirstTime`
            """)
            print("vision_lanes table updated successfully.")

        # Alter vision_samples
        print("Checking/altering vision_samples table...")
        cur.execute("SHOW COLUMNS FROM `vision_samples` LIKE 'origin_SampTime'")
        if cur.fetchone():
            print("origin_SampTime column already exists in vision_samples.")
        else:
            print("Adding origin_SampTime column to vision_samples...")
            cur.execute("""
                ALTER TABLE `vision_samples`
                ADD COLUMN `origin_SampTime` datetime DEFAULT NULL COMMENT 'Raw source SampTime, before clock correction' AFTER `SampTime`
            """)
            print("vision_samples table updated successfully.")

    conn.commit()
    print("Database migration completed successfully!")
    print("Note: existing rows keep NULL origin_* values - only rows re-synced after this point are backfilled.")
except Exception as e:
    print(f"Migration error: {e}")
    conn.rollback()
finally:
    conn.close()
