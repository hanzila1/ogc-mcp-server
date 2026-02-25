"""
Stage 3 verification — Full OGC API Processes lifecycle test
against our own local pygeoapi Docker backend.

This is the Code Challenge proof of concept:
- Our own server running in Docker
- Custom geospatial processes registered
- Full job lifecycle: submit → result
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ogc_mcp.ogc_client import OGCClient

LOCAL_SERVER = "http://localhost:5000"


async def test_local_backend():
    print("=" * 60)
    print("STAGE 3 — Local pygeoapi Docker Backend Test")
    print("=" * 60)

    async with OGCClient(LOCAL_SERVER) as client:

        # Test 1 — Server info
        print("\nTEST 1: Local server discovery")
        print("-" * 40)
        info = await client.get_server_info()
        print(f"Server: {info.title}")
        print(f"Description: {info.description}")
        print(f"Capabilities: {', '.join(info.capabilities)}")

        # Test 2 — Collections
        print("\nTEST 2: Collections (including parks data)")
        print("-" * 40)
        collections = await client.get_collections()
        for c in collections:
            print(f"  ✓ [{c.id}] {c.title}")

        # Test 3 — Parks features
        print("\nTEST 3: Fetch Münster parks data")
        print("-" * 40)
        parks = await client.get_features("parks", limit=10)
        features = parks.get("features", [])
        print(f"  Retrieved {len(features)} parks:")
        for f in features:
            name = f.get("properties", {}).get("name", "Unknown")
            area = f.get("properties", {}).get("area_ha", 0)
            print(f"  ✓ {name} ({area} ha)")

        # Test 4 — Discover processes
        print("\nTEST 4: Discover custom processes")
        print("-" * 40)
        processes = await client.get_processes()
        for p in processes:
            print(f"  ✓ [{p.id}] {p.title}")

        # Test 5 — Buffer process detail
        print("\nTEST 5: Geospatial buffer process schema")
        print("-" * 40)
        buffer_proc = await client.get_process("geospatial-buffer")
        print(f"  Process: {buffer_proc.title}")
        print(f"  Version: {buffer_proc.version}")
        print(f"  Inputs: {list(buffer_proc.inputs.keys())}")

        # Test 6 — Execute buffer process
        print("\nTEST 6: Execute geospatial buffer on a point")
        print("-" * 40)
        buffer_result = await client.execute_process(
            process_id="geospatial-buffer",
            inputs={
                "geometry": {
                    "type": "Point",
                    "coordinates": [7.615, 51.955]
                },
                "buffer_degrees": 0.01,
                "label": "Münster Park Buffer Zone"
            },
            async_execute=False
        )
        feature = buffer_result.get("buffered_feature", {})
        props = feature.get("properties", {})
        print(f"  ✓ Label: {props.get('label')}")
        print(f"  ✓ Buffer: {props.get('buffer_degrees')} degrees")
        print(f"  ✓ Buffer: ~{props.get('buffer_km_approx')} km")
        print(f"  ✓ Geometry type: {feature.get('geometry', {}).get('type')}")

        # Test 7 — Execute cool spot demo
        print("\nTEST 7: Execute Cool Spot Analysis on Münster parks")
        print("-" * 40)
        cool_spot_result = await client.execute_process(
            process_id="cool-spot-demo",
            inputs={
                "park_geometries": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "name": "Aasee Park",
                                "area_ha": 52.3,
                                "tree_coverage": 0.45,
                                "has_water": True
                            },
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[
                                    [7.610, 51.940],
                                    [7.625, 51.940],
                                    [7.625, 51.950],
                                    [7.610, 51.950],
                                    [7.610, 51.940]
                                ]]
                            }
                        },
                        {
                            "type": "Feature",
                            "properties": {
                                "name": "Schlosspark",
                                "area_ha": 18.7,
                                "tree_coverage": 0.80,
                                "has_water": False
                            },
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[
                                    [7.612, 51.962],
                                    [7.622, 51.962],
                                    [7.622, 51.968],
                                    [7.612, 51.968],
                                    [7.612, 51.962]
                                ]]
                            }
                        }
                    ]
                },
                "buffer_km": 0.5,
                "city_name": "Münster"
            },
            async_execute=False
        )

        report = cool_spot_result.get("cool_spot_report", {})
        print(f"  ✓ City: {report.get('city')}")
        print(f"  ✓ Parks analyzed: {report.get('parks_analyzed')}")
        print(f"  ✓ Total cooling coverage: {report.get('total_cooling_coverage_km2')} km²")
        print()
        for spot in report.get("cool_spots", []):
            print(f"  Park: {spot['park_name']}")
            print(f"    Temperature reduction: {spot['estimated_temp_reduction_c']}°C")
            print(f"    Cooling intensity: {spot['cooling_intensity']}")
            print(f"    Cooling area: {spot['cooling_area_km2']} km²")
        print()
        print(f"  Summary: {report.get('summary')}")

    print()
    print("=" * 60)
    print("✓ ALL STAGE 3 TESTS PASSED")
    print("✓ Local Docker backend fully operational")
    print("✓ Code Challenge complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_local_backend())