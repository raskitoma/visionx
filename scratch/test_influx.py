import os
from influxdb_client import InfluxDBClient
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("INFLUX_HOST", "http://influxdb:8086")
token = os.getenv("INFLUX_TOKEN", "")
org = os.getenv("INFLUX_ORG", "")
bucket = os.getenv("INFLUX_BUCKET", "visionx")

query = f'''
from(bucket: "{bucket}")
  |> range(start: -60m)
  |> filter(fn: (r) => r["_measurement"] == "production_run")
  |> filter(fn: (r) => r["_field"] == "nDetected" or r["_field"] == "nPassed" or r["_field"] == "nMarginal" or r["_field"] == "nRejected")
  |> spread()
'''

print(f"Connecting to {url}...")
try:
    with InfluxDBClient(url=url, token=token, org=org, timeout=10000) as client:
        query_api = client.query_api()
        tables = query_api.query(query)
        for table in tables:
            for record in table.records:
                print(f"Line: {record.values.get('line')}, Field: {record.get_field()}, Value: {record.get_value()}")
except Exception as e:
    print(f"Error: {e}")
