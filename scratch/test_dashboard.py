import urllib.request
import json

BASE_URL = "http://localhost:8001"  # Host port mapping to container 8000

def test_runs():
    print("Testing GET /api/runs...")
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/runs") as response:
            print(f"Status: {response.status}")
            data = json.loads(response.read().decode())
            print(f"Number of lines: {len(data)}")
            for line, info in data.items():
                print(f"  Line {line}: Product={info.get('ProductId')}, isRunning={info.get('isRunning')}")
                print(f"  Averages 30m: {json.dumps(info.get('averages_30m'), indent=2)}")
    except Exception as e:
        print(f"Failed: {e}")

def test_products():
    print("\nTesting GET /api/products...")
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/products") as response:
            print(f"Status: {response.status}")
            data = json.loads(response.read().decode())
            for line, prods in data.items():
                print(f"  Line {line}: {len(prods)} products synced.")
                if prods:
                    print(f"    Sample Product: {prods[0]['ProductId']} - {prods[0]['ProductDesc']}")
    except Exception as e:
        print(f"Failed: {e}")

def test_alerts():
    print("\nTesting GET /api/alerts...")
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/alerts") as response:
            print(f"Status: {response.status}")
            data = json.loads(response.read().decode())
            print(f"Returned {len(data)} alerts.")
            for item in data[:5]:
                print(f"  [{item['AlertTime']}] Line {item['SourceLine']} Run {item['RunId']}: {item['Details']}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_runs()
    test_products()
    test_alerts()
