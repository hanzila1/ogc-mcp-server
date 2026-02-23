import httpx
import json

BASE_URL = "https://demo.pygeoapi.io/master"

def pretty(data):
    print(json.dumps(data, indent=2))

def explore():
    client = httpx.Client()

    # 1. Discover what this server offers
    print("=== LANDING PAGE ===")
    r = client.get(f"{BASE_URL}/")
    landing = r.json()
    print(f"Server title: {landing.get('title')}")
    print(f"Available links: {[l['rel'] for l in landing.get('links', [])]}")

    # 2. Discover all collections dynamically
    print("\n=== COLLECTIONS (what data is available?) ===")
    r = client.get(f"{BASE_URL}/collections")
    collections = r.json()
    for col in collections.get("collections", [])[:5]:
        print(f"  - {col['id']}: {col.get('title', 'no title')}")

    # 3. Get actual features from lakes collection
    print("\n=== SAMPLE FEATURES (lakes) ===")
    r = client.get(f"{BASE_URL}/collections/lakes/items?limit=2")
    features = r.json()
    for f in features.get("features", []):
        print(f"  - {f['properties'].get('name', 'unnamed')}")

    # 4. Discover available processes
    print("\n=== PROCESSES (what can this server DO?) ===")
    r = client.get(f"{BASE_URL}/processes")
    processes = r.json()
    for p in processes.get("processes", []):
        print(f"  - {p['id']}: {p.get('title', 'no title')}")

    # 5. Get full details of hello-world process
    print("\n=== PROCESS INPUTS/OUTPUTS SCHEMA ===")
    r = client.get(f"{BASE_URL}/processes/hello-world")
    process_detail = r.json()
    print("Inputs required:")
    for name, schema in process_detail.get("inputs", {}).items():
        print(f"  - {name} ({schema['schema']['type']}): {schema.get('description', '')}")

    # 6. Execute the process
    print("\n=== EXECUTING PROCESS ===")
    payload = {
        "inputs": {
            "name": "GSoC MCP Project",
            "message": "MCP + OGC = Future of GeoAI"
        }
    }
    r = client.post(
        f"{BASE_URL}/processes/hello-world/execution",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    result = r.json()
    print(f"Result: {result}")

if __name__ == "__main__":
    explore()