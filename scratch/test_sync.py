import sys
import os

# Ensure app directory is in Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '../app'))

import pymysql
from sync_engine import run_sync, get_target_connection

def run_test():
    print("Running sync cycle...")
    run_sync()
    
    print("\nChecking synced products in the target database...")
    conn = get_target_connection()
    if not conn:
        print("Error: Could not connect to target database")
        return
        
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT SourceLine, ProductId, ProductDesc, D1Min, D1Max, LastUpdate FROM vision_product LIMIT 10")
            products = cur.fetchall()
            
            if products:
                print(f"Success! Synced {len(products)} products to vision_product:")
                for p in products:
                    print(f"  Line: {p['SourceLine']} | Product: {p['ProductId']} | Desc: {p['ProductDesc']} | D1Min: {p['D1Min']} | D1Max: {p['D1Max']} | LastUpdate: {p['LastUpdate']}")
            else:
                print("No products found in vision_product table.")
    except Exception as e:
        print(f"Error querying vision_product: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_test()
