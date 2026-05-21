import sys
import os
import pytz
from datetime import datetime, timedelta

# Ensure app directory is in Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '../app'))

import pymysql
from sync_engine import get_target_connection
from alert_system import run_alert_check

def run_test():
    print("Connecting to target database...")
    conn = get_target_connection()
    if not conn:
        print("Error: Could not connect to target database")
        return
        
    try:
        with conn.cursor() as cur:
            # 1. Clean up any existing test records to start fresh
            cur.execute("DELETE FROM vision_alert_history WHERE SourceLine = 'TEST_LINE'")
            cur.execute("DELETE FROM vision_product WHERE SourceLine = 'TEST_LINE'")
            cur.execute("DELETE FROM vision_runs WHERE SourceLine = 'TEST_LINE'")
            cur.execute("DELETE FROM vision_samples WHERE SourceLine = 'TEST_LINE'")
            conn.commit()
            print("Cleaned up old test data.")
            
            # 2. Insert mock product spec
            print("Inserting mock product spec...")
            cur.execute("""
                INSERT INTO vision_product (
                    SourceLine, ProductId, ProductDesc, Elliptic, 
                    D1Min, D1Max, ToastMin, RawMax
                ) VALUES (
                    'TEST_LINE', 'TEST_PROD', 'Test Product Specs', 0,
                    10.0, 20.0, 15.0, 5.0
                )
            """)
            
            # 3. Insert mock run and samples violating spec limits:
            # - DMajorAverage is 5.0 (below D1Min 10.0)
            # - ToastAverage is 1200.0 (12.0%, below ToastMin 15.0%)
            # - RawAverage is 800.0 (8.0%, above RawMax 5.0%)
            print("Inserting mock run violating spec limits...")
            ny_tz = pytz.timezone('America/New_York')
            now_ny = datetime.now(ny_tz)
            now_naive = now_ny.replace(tzinfo=None)
            
            cur.execute("""
                INSERT INTO vision_runs (
                    SourceLine, RunId, StartTime, ProductId, 
                    DMajorAverage, ToastAverage, RawAverage, LastUpdate
                ) VALUES (
                    'TEST_LINE', 9999, %s, 'TEST_PROD',
                    5.0, 1200.0, 800.0, %s
                )
            """, (now_naive, now_naive))
            
            print("Inserting mock sample violating spec limits...")
            cur.execute("""
                INSERT INTO vision_samples (
                    SourceLine, RunId, LaneId, SampNo, SampTime,
                    DMajorAverage, DAvgAverage, ToastAverage, RawAverage
                ) VALUES (
                    'TEST_LINE', 9999, '*', 1, %s,
                    5.0, 5.0, 1200.0, 800.0
                )
            """, (now_naive,))
            conn.commit()
            print("Mock database setup complete.")
            
        # 4. Run the alert checker
        print("\n--- Running alert verification check ---\n")
        run_alert_check()
        print("\n--- Alert verification check completed ---\n")
        
        # 5. Query and verify alert history
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM vision_alert_history WHERE SourceLine = 'TEST_LINE'")
            alerts = cur.fetchall()
            
            if alerts:
                print(f"Success! Found {len(alerts)} alerts in history table:")
                for alert in alerts:
                    print(f"  ID: {alert['id']}")
                    print(f"  Line: {alert['SourceLine']}")
                    print(f"  Time: {alert['AlertTime']}")
                    print(f"  Run ID: {alert['RunId']}")
                    print(f"  Product ID: {alert['ProductId']}")
                    print(f"  Details: {alert['Details']}")
                    print(f"  SlackSentTime: {alert.get('SlackSentTime')}")
            else:
                print("Error: No alerts found in vision_alert_history for TEST_LINE")
                
            # 6. Clean up mock records
            print("\nCleaning up test records from database...")
            cur.execute("DELETE FROM vision_alert_history WHERE SourceLine = 'TEST_LINE'")
            cur.execute("DELETE FROM vision_product WHERE SourceLine = 'TEST_LINE'")
            cur.execute("DELETE FROM vision_runs WHERE SourceLine = 'TEST_LINE'")
            cur.execute("DELETE FROM vision_samples WHERE SourceLine = 'TEST_LINE'")
            conn.commit()
            print("Cleanup completed.")
            
    except Exception as e:
        print(f"Exception during test: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_test()
