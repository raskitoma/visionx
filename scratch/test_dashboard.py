import requests
import json

BASE_URL = "http://localhost:8001"

def test_runs():
    print("Testing GET /api/runs...")
    try:
        r = requests.get(f"{BASE_URL}/api/runs")
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"Number of lines: {len(data)}")
            for line, info in data.items():
                print(f"  Line {line}: Product={info.get('ProductId')}, isRunning={info.get('isRunning')}")
                print(f"  Averages 30m: {json.dumps(info.get('averages_30m'), indent=2)}")
        else:
            print(r.text)
    except Exception as e:
        print(f"Failed: {e}")

def test_products():
    print("\nTesting GET /api/products...")
    try:
        r = requests.get(f"{BASE_URL}/api/products")
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            for line, prods in data.items():
                print(f"  Line {line}: {len(prods)} products synced.")
                if prods:
                    print(f"    Sample Product: {prods[0]['ProductId']} - {prods[0]['ProductDesc']}")
        else:
            print(r.text)
    except Exception as e:
        print(f"Failed: {e}")

def test_alerts():
    print("\nTesting GET /api/alerts...")
    try:
        r = requests.get(f"{BASE_URL}/api/alerts")
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"Returned {len(data)} alerts.")
            for item in data[:5]:
                print(f"  [{item['AlertTime']}] Line {item['SourceLine']} Run {item['RunId']}: {item['Details']}")
        else:
            print(r.text)
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_runs()
    test_products()
    test_alerts()
