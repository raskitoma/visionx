import os
import pymysql
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

def init_db():
    target_db_raw = os.getenv("TARGET_DB")
    if not target_db_raw:
        print("Error: TARGET_DB environment variable not set.")
        return

    try:
        # Format: user:password@host:port/dbname
        user_pass, host_port_db = target_db_raw.split('@')
        user, password = user_pass.split(':')
        host_port, dbname = host_port_db.split('/')
        host, port = host_port.split(':')
        port = int(port)
    except Exception as e:
        print(f"Error parsing TARGET_DB: {e}")
        return

    if not os.path.exists("init.sql"):
        # Check if we are in /app or project root
        if os.path.exists("../init.sql"):
            sql_path = "../init.sql"
        else:
            print("Error: init.sql not found.")
            return
    else:
        sql_path = "init.sql"

    print(f"Connecting to {host}:{port}/{dbname}...")
    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=dbname,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS
        )
        
        with connection.cursor() as cursor:
            with open(sql_path, 'r') as f:
                sql = f.read()
                print("Executing init.sql...")
                cursor.execute(sql)
            connection.commit()
            print("Database initialization successful.")
            
    except Exception as e:
        print(f"Database initialization failed: {e}")
    finally:
        if 'connection' in locals():
            connection.close()

if __name__ == "__main__":
    init_db()
