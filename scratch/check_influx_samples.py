import os
import sys
from influxdb_client import InfluxDBClient
# Load dotenv if running locally, otherwise rely on environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

url = os.getenv("INFLUX_HOST", "http://influxdb:8086")
token = os.getenv("INFLUX_TOKEN", "")
org = os.getenv("INFLUX_ORG", "")
bucket = os.getenv("INFLUX_BUCKET", "visionx")

query = f'''
from(bucket: "{bucket}")
  |> range(start: -30d)
  |> filter(fn: (r) => r["_measurement"] == "production_sample")
  |> limit(n: 100)
'''

print(f"Connecting to InfluxDB at {url}...")
try:
    with InfluxDBClient(url=url, token=token, org=org, timeout=10000) as client:
        query_api = client.query_api()
        tables = query_api.query(query)
        
        records_by_time_lane = {}
        for table in tables:
            for record in table.records:
                time_key = record.get_time()
                lane = record.values.get('lane')
                line = record.values.get('line')
                run_id = record.values.get('RunId')
                key = (time_key, lane, line, run_id)
                
                if key not in records_by_time_lane:
                    records_by_time_lane[key] = {}
                
                field_name = record.get_field()
                field_value = record.get_value()
                records_by_time_lane[key][field_name] = field_value

        if not records_by_time_lane:
            print("No samples found in the last 1 hour.")
        else:
            print(f"Found {len(records_by_time_lane)} sample data points.")
            print("\nSample records:")
            for i, (key, fields) in enumerate(list(records_by_time_lane.items())[:5]):
                time_key, lane, line, run_id = key
                print(f"Record {i+1}:")
                print(f"  Time: {time_key}")
                print(f"  Line: {line} | Lane: {lane} | RunId: {run_id}")
                print(f"  Fields: {fields}")
except Exception as e:
    print(f"Error querying InfluxDB: {e}")
