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
        cur.execute("SHOW COLUMNS FROM `vision_runs` LIKE 'TargetDMajor'")
        if cur.fetchone():
            print("TargetDMajor column already exists in vision_runs.")
        else:
            print("Adding TargetDMajor, TargetDMinor, and TargetDAvg columns to vision_runs...")
            cur.execute("""
                ALTER TABLE `vision_runs` 
                ADD COLUMN `TargetDMajor` double DEFAULT NULL AFTER `nRejected`, 
                ADD COLUMN `TargetDMinor` double DEFAULT NULL AFTER `TargetDMajor`, 
                ADD COLUMN `TargetDAvg` double DEFAULT NULL AFTER `TargetDMinor`
            """)
            print("vision_runs table updated successfully.")

        # Alter vision_samples
        print("Checking/altering vision_samples table...")
        cur.execute("SHOW COLUMNS FROM `vision_samples` LIKE 'TargetDMajor'")
        if cur.fetchone():
            print("TargetDMajor column already exists in vision_samples.")
        else:
            print("Adding TargetDMajor, TargetDMinor, and TargetDAvg columns to vision_samples...")
            cur.execute("""
                ALTER TABLE `vision_samples` 
                ADD COLUMN `TargetDMajor` double DEFAULT NULL AFTER `nRejected`, 
                ADD COLUMN `TargetDMinor` double DEFAULT NULL AFTER `TargetDMajor`, 
                ADD COLUMN `TargetDAvg` double DEFAULT NULL AFTER `TargetDMinor`
            """)
            print("vision_samples table updated successfully.")
            
    conn.commit()
    print("Database migration completed successfully!")
except Exception as e:
    print(f"Migration error: {e}")
    conn.rollback()
finally:
    conn.close()
