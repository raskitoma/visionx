import os
import sys
from influxdb_client import InfluxDBClient

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

url = os.getenv("INFLUX_HOST", "http://influxdb:8086")
token = os.getenv("INFLUX_TOKEN", "")
org = os.getenv("INFLUX_ORG", "")
bucket = os.getenv("INFLUX_BUCKET", "visionx")

def check_measurement(measurement_name):
    print(f"\n--- Checking latest points in '{measurement_name}' ---")
    query = f'''
    from(bucket: "{bucket}")
      |> range(start: -30m)
      |> filter(fn: (r) => r["_measurement"] == "{measurement_name}")
      |> filter(fn: (r) => r["_field"] == "TargetDMajor" or r["_field"] == "TargetDMinor" or r["_field"] == "TargetDAvg" or r["_field"] == "nDetected")
    '''
    try:
        with InfluxDBClient(url=url, token=token, org=org, timeout=10000) as client:
            query_api = client.query_api()
            tables = query_api.query(query)
            
            records_by_time = {}
            for table in tables:
                for record in table.records:
                    time_key = record.get_time()
                    line = record.values.get('line')
                    run_id = record.values.get('RunId')
                    lane = record.values.get('lane', '*')
                    
                    key = (time_key, line, run_id, lane)
                    if key not in records_by_time:
                        records_by_time[key] = {}
                        
                    records_by_time[key][record.get_field()] = record.get_value()
            
            if not records_by_time:
                print("No recent data points found with target dimension fields in InfluxDB.")
            else:
                print(f"Found {len(records_by_time)} recent points with these fields.")
                for i, (key, fields) in enumerate(list(records_by_time.items())[:5]):
                    time_key, line, run_id, lane = key
                    print(f"Point {i+1}: Time={time_key} | Line={line} | RunId={run_id} | Lane={lane}")
                    print(f"  Fields: {fields}")
    except Exception as e:
        print(f"Error querying InfluxDB for {measurement_name}: {e}")

check_measurement("production_run")
check_measurement("production_sample")
