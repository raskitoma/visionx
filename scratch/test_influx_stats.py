import os
from influxdb_client import InfluxDBClient
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("INFLUX_HOST", "http://localhost:8086")
token = os.getenv("INFLUX_TOKEN", "")
org = os.getenv("INFLUX_ORG", "visionx")
bucket = os.getenv("INFLUX_BUCKET", "visionx")

query = f'''
from(bucket: "{bucket}")
  |> range(start: -60m)
  |> filter(fn: (r) => r["_measurement"] == "production_run")
  |> filter(fn: (r) => r["_field"] == "nDetected" or r["_field"] == "nPassed" or r["_field"] == "nMarginal" or r["_field"] == "nRejected")
  |> group(columns: ["line", "_field"])
  |> difference()
  |> filter(fn: (r) => r._value >= 0)
  |> sum()
'''

print(f"Connecting to {url}...")
try:
    with InfluxDBClient(url=url, token=token, org=org) as client:
        query_api = client.query_api()
        result = query_api.query(query=query)
        
        stats = {}
        for table in result:
            for record in table.records:
                line = record.values.get("line")
                field = record.get_field()
                value = record.get_value()
                if line not in stats:
                    stats[line] = {}
                stats[line][field] = value
        
        print("Hourly Stats Result:")
        import json
        print(json.dumps(stats, indent=2))
except Exception as e:
    print(f"Error: {e}")
