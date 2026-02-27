"""
Stage 5 — End-to-End Integration Test

This is the ULTIMATE proof of concept. It connects to the MCP server
as an LLM client would, and executes the complete cool spot analysis
workflow against the local Docker backend — exactly the scenario
from the GSoC project description.

Flow:
  MCP Client → MCP Server (our server.py) → OGC API (Docker pygeoapi)

Unlike test_stage3.py which called OGCClient directly, this test
goes through the full MCP protocol — proving the entire stack works
end-to-end.

Prerequisites:
  1. Docker backend running: docker run -p 5000:80 --name ogc-backend ogc-mcp-pygeoapi
  2. From project root: python examples/test_stage5_e2e.py

License: Apache Software License, Version 2.0
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Local Docker backend URL
LOCAL_SERVER = "http://localhost:5000"

# Track test results
passed = 0
failed = 0
errors = []


def check(test_name: str, condition: bool, detail: str = ""):
    """Record a test result."""
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {test_name}")
    else:
        failed += 1
        msg = f"  ✗ {test_name}" + (f" — {detail}" if detail else "")
        print(msg)
        errors.append(msg)


async def run_e2e_test():
    global passed, failed

    print("=" * 70)
    print("STAGE 5 — End-to-End MCP Integration Test")
    print("MCP Client → MCP Server → Docker pygeoapi Backend")
    print("=" * 70)

    # Connect to MCP server via stdio transport
    # This is exactly how Claude Desktop or any MCP client connects
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(os.path.dirname(__file__), '..', 'main.py')],
        env={
            **os.environ,
            "OGC_SERVER_URL": LOCAL_SERVER
        }
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ════════════════════════════════════════════════
            # TEST 1: MCP Server Initialization
            # ════════════════════════════════════════════════
            print("\n── TEST 1: MCP Server Initialization ──")

            # List tools
            tools_result = await session.list_tools()
            tools = tools_result.tools
            tool_names = [t.name for t in tools]
            print(f"  Tools registered: {len(tools)}")
            check("Has discover_ogc_server tool", "discover_ogc_server" in tool_names)
            check("Has get_collections tool", "get_collections" in tool_names)
            check("Has get_features tool", "get_features" in tool_names)
            check("Has discover_processes tool", "discover_processes" in tool_names)
            check("Has execute_process tool", "execute_process" in tool_names)
            check("Has get_job_status tool", "get_job_status" in tool_names)

            # List resources
            resources_result = await session.list_resources()
            resources = resources_result.resources
            print(f"  Resources registered: {len(resources)}")
            check("Has at least 1 resource", len(resources) >= 1)

            # List prompts
            prompts_result = await session.list_prompts()
            prompts = prompts_result.prompts
            prompt_names = [p.name for p in prompts]
            print(f"  Prompts registered: {len(prompts)}")
            check("Has workflow prompts", len(prompts) >= 1)

            # ════════════════════════════════════════════════
            # TEST 2: Discover Local Docker Backend
            # ════════════════════════════════════════════════
            print("\n── TEST 2: Discover Local Docker Backend ──")

            result = await session.call_tool(
                "discover_ogc_server",
                {"server_url": LOCAL_SERVER}
            )
            server_text = result.content[0].text
            print(f"  Server response:\n    {server_text[:200]}")
            check("Server responds", len(server_text) > 0)
            check("Is our GSoC backend", "GSoC" in server_text or "MCP" in server_text)
            check("Has processes capability", "processes" in server_text.lower())

            # ════════════════════════════════════════════════
            # TEST 3: List Collections — Find Parks
            # ════════════════════════════════════════════════
            print("\n── TEST 3: List Collections ──")

            result = await session.call_tool(
                "get_collections",
                {"server_url": LOCAL_SERVER}
            )
            collections_text = result.content[0].text
            print(f"  Collections response:\n    {collections_text[:200]}")
            check("Collections returned", len(collections_text) > 0)
            check("Parks collection exists", "parks" in collections_text.lower())

            # ════════════════════════════════════════════════
            # TEST 4: Fetch Münster Park Features
            # ════════════════════════════════════════════════
            print("\n── TEST 4: Fetch Park Features ──")

            result = await session.call_tool(
                "get_features",
                {
                    "server_url": LOCAL_SERVER,
                    "collection_id": "parks",
                    "limit": 10
                }
            )
            features_text = result.content[0].text
            print(f"  Features response:\n    {features_text[:300]}")
            check("Features returned", len(features_text) > 0)
            check("Contains Aasee Park", "Aasee" in features_text)
            check("Contains Schlosspark", "Schlosspark" in features_text)
            check("Has geometry data", "Polygon" in features_text or "polygon" in features_text or "coordinates" in features_text)

            # ════════════════════════════════════════════════
            # TEST 5: Discover Available Processes
            # ════════════════════════════════════════════════
            print("\n── TEST 5: Discover Processes ──")

            result = await session.call_tool(
                "discover_processes",
                {"server_url": LOCAL_SERVER}
            )
            processes_text = result.content[0].text
            print(f"  Processes response:\n    {processes_text[:300]}")
            check("Processes returned", len(processes_text) > 0)
            check("Has geospatial-buffer", "geospatial-buffer" in processes_text or "buffer" in processes_text.lower())
            check("Has cool-spot-demo", "cool-spot-demo" in processes_text or "cool" in processes_text.lower())

            # ════════════════════════════════════════════════
            # TEST 6: Inspect Cool Spot Process Schema
            # ════════════════════════════════════════════════
            print("\n── TEST 6: Cool Spot Process Schema ──")

            result = await session.call_tool(
                "get_process_detail",
                {
                    "server_url": LOCAL_SERVER,
                    "process_id": "cool-spot-demo"
                }
            )
            schema_text = result.content[0].text
            print(f"  Process detail:\n    {schema_text[:300]}")
            check("Schema returned", len(schema_text) > 0)
            check("Has park_geometries input", "park_geometries" in schema_text or "parks" in schema_text.lower())
            check("Describes cool spot analysis", "cool" in schema_text.lower() or "temperature" in schema_text.lower())

            # ════════════════════════════════════════════════
            # TEST 7: Execute Geospatial Buffer
            # ════════════════════════════════════════════════
            print("\n── TEST 7: Execute Geospatial Buffer ──")

            result = await session.call_tool(
                "execute_process",
                {
                    "server_url": LOCAL_SERVER,
                    "process_id": "geospatial-buffer",
                    "inputs": {
                        "geometry": {
                            "type": "Point",
                            "coordinates": [7.6261, 51.9607]
                        },
                        "buffer_degrees": 0.01,
                        "label": "Münster City Center Buffer"
                    }
                }
            )
            buffer_text = result.content[0].text
            print(f"  Buffer result:\n    {buffer_text[:300]}")
            check("Buffer executed", len(buffer_text) > 0)
            check("No error in response", "error" not in buffer_text.lower() or "Error" not in buffer_text[:10])
            check("Returns geometry", "Polygon" in buffer_text or "polygon" in buffer_text or "coordinates" in buffer_text)

            # ════════════════════════════════════════════════
            # TEST 8: Execute Cool Spot Analysis
            # The Project Description Scenario!
            # ════════════════════════════════════════════════
            print("\n── TEST 8: Cool Spot Analysis (The GSoC Scenario!) ──")

            cool_spot_inputs = {
                "park_geometries": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"name": "Aasee Park", "area_ha": 52.3},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[
                                    [7.607, 51.949],
                                    [7.617, 51.949],
                                    [7.617, 51.957],
                                    [7.607, 51.957],
                                    [7.607, 51.949]
                                ]]
                            }
                        },
                        {
                            "type": "Feature",
                            "properties": {"name": "Schlosspark", "area_ha": 18.7},
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
            }

            result = await session.call_tool(
                "execute_process",
                {
                    "server_url": LOCAL_SERVER,
                    "process_id": "cool-spot-demo",
                    "inputs": cool_spot_inputs
                }
            )
            cool_text = result.content[0].text
            print(f"  Cool spot result:\n    {cool_text[:500]}")
            check("Cool spot executed", len(cool_text) > 0)
            check("No error", "error" not in cool_text.lower() or "Error" not in cool_text[:10])
            check("Contains Aasee Park results", "Aasee" in cool_text)
            check("Contains Schlosspark results", "Schlosspark" in cool_text)
            check("Contains temperature data", "°C" in cool_text or "temp" in cool_text.lower() or "reduction" in cool_text.lower())
            check("Contains coverage data", "km²" in cool_text or "km2" in cool_text or "coverage" in cool_text.lower())

            # ════════════════════════════════════════════════
            # TEST 9: Read a Resource (Collection Metadata)
            # ════════════════════════════════════════════════
            print("\n── TEST 9: Read Collection Resource ──")

            if len(resources) > 0:
                resource_uri = resources[0].uri
                print(f"  Reading resource: {resource_uri}")
                resource_content = await session.read_resource(resource_uri)
                resource_text = resource_content.contents[0].text if resource_content.contents else ""
                print(f"  Resource content:\n    {resource_text[:200]}")
                check("Resource readable", len(resource_text) > 0)
            else:
                print("  No resources available — skipping")
                check("Resource readable", False, "No resources registered")

            # ════════════════════════════════════════════════
            # TEST 10: Get a Workflow Prompt
            # ════════════════════════════════════════════════
            print("\n── TEST 10: Workflow Prompt ──")

            if len(prompt_names) > 0:
                prompt_name = prompt_names[0]
                print(f"  Getting prompt: {prompt_name}")
                try:
                    prompt_result = await session.get_prompt(
                        prompt_name,
                        {
                            "server_url": LOCAL_SERVER,
                            "analysis_goal": "cool spot analysis for Münster parks"
                        }
                    )
                    prompt_text = prompt_result.messages[0].content.text if prompt_result.messages else ""
                    print(f"  Prompt content:\n    {prompt_text[:200]}")
                    check("Prompt returned", len(prompt_text) > 0)
                    check("Prompt mentions analysis", "analysis" in prompt_text.lower() or "process" in prompt_text.lower() or "step" in prompt_text.lower())
                except Exception as e:
                    print(f"  Prompt call failed: {e}")
                    check("Prompt returned", False, str(e))
                    check("Prompt mentions analysis", False, "skipped")
            else:
                print("  No prompts available — skipping")
                check("Prompt returned", False, "No prompts registered")
                check("Prompt mentions analysis", False, "skipped")

    # ════════════════════════════════════════════════
    # SUMMARY
    # ════════════════════════════════════════════════
    total = passed + failed
    print("\n" + "=" * 70)
    print(f"STAGE 5 END-TO-END RESULTS: {passed}/{total} checks passed")
    print("=" * 70)

    if failed > 0:
        print(f"\n⚠ {failed} checks failed:")
        for e in errors:
            print(f"  {e}")
    else:
        print("\n✓ ALL CHECKS PASSED")
        print("✓ MCP Client → MCP Server → Docker Backend — FULL STACK VERIFIED")
        print("✓ Cool spot analysis scenario working end-to-end through MCP!")

    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_e2e_test())
    sys.exit(0 if success else 1)
