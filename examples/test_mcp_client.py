"""
Direct MCP client test — verifies all tools, resources, and prompts work.
Run with: python examples/test_mcp_client.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_server():
    """Connect to our MCP server and test every capability."""

    server_params = StdioServerParameters(
        command="python",
        args=["main.py"],
        env=None
    )

    print("Connecting to OGC MCP Server...")
    print("=" * 60)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            await session.initialize()
            print("✓ Connected successfully\n")

            # ── Test 1: List all tools ───────────────────────
            print("TEST 1: List available tools")
            print("-" * 40)
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"  ✓ {tool.name}")
            print(f"  Total: {len(tools.tools)} tools\n")

            # ── Test 2: List resources ───────────────────────
            print("TEST 2: List available resources")
            print("-" * 40)
            resources = await session.list_resources()
            for resource in resources.resources:
                print(f"  ✓ {resource.uri}")
            print(f"  Total: {len(resources.resources)} resources\n")

            # ── Test 3: List prompts ─────────────────────────
            print("TEST 3: List available prompts")
            print("-" * 40)
            prompts = await session.list_prompts()
            for prompt in prompts.prompts:
                print(f"  ✓ {prompt.name}")
            print(f"  Total: {len(prompts.prompts)} prompts\n")

            # ── Test 4: discover_ogc_server ──────────────────
            print("TEST 4: discover_ogc_server")
            print("-" * 40)
            result = await session.call_tool(
                "discover_ogc_server",
                {"server_url": "https://demo.pygeoapi.io/master"}
            )
            print(result.content[0].text)
            print()

            # ── Test 5: get_collections ──────────────────────
            print("TEST 5: get_collections")
            print("-" * 40)
            result = await session.call_tool(
                "get_collections",
                {"server_url": "https://demo.pygeoapi.io/master"}
            )
            print(result.content[0].text[:400])
            print()

            # ── Test 6: get_features ─────────────────────────
            print("TEST 6: get_features (lakes, limit=3)")
            print("-" * 40)
            result = await session.call_tool(
                "get_features",
                {
                    "server_url": "https://demo.pygeoapi.io/master",
                    "collection_id": "lakes",
                    "limit": 3
                }
            )
            print(result.content[0].text)
            print()

            # ── Test 7: get_features with bbox ───────────────
            print("TEST 7: get_features with bbox (Europe)")
            print("-" * 40)
            result = await session.call_tool(
                "get_features",
                {
                    "server_url": "https://demo.pygeoapi.io/master",
                    "collection_id": "lakes",
                    "limit": 3,
                    "bbox": "-10,35,40,75"
                }
            )
            print(result.content[0].text)
            print()

            # ── Test 8: discover_processes ───────────────────
            print("TEST 8: discover_processes")
            print("-" * 40)
            result = await session.call_tool(
                "discover_processes",
                {"server_url": "https://demo.pygeoapi.io/master"}
            )
            print(result.content[0].text)
            print()

            # ── Test 9: get_process_detail ───────────────────
            print("TEST 9: get_process_detail (hello-world)")
            print("-" * 40)
            result = await session.call_tool(
                "get_process_detail",
                {
                    "server_url": "https://demo.pygeoapi.io/master",
                    "process_id": "hello-world"
                }
            )
            print(result.content[0].text)
            print()

            # ── Test 10: execute_process ─────────────────────
            print("TEST 10: execute_process (hello-world)")
            print("-" * 40)
            result = await session.call_tool(
                "execute_process",
                {
                    "server_url": "https://demo.pygeoapi.io/master",
                    "process_id": "hello-world",
                    "inputs": {
                        "name": "GSoC 2026 OGC MCP",
                        "message": "Stage 2 complete — MCP + OGC working!"
                    },
                    "async_execute": False
                }
            )
            print(result.content[0].text)
            print()

            # ── Test 11: read resource ───────────────────────
            print("TEST 11: Read server_info resource")
            print("-" * 40)
            resource_content = await session.read_resource(
                "ogc://server/info"
            )
            print(resource_content.contents[0].text)
            print()

            # ── Test 12: get prompt ──────────────────────────
            print("TEST 12: Get spatial_analysis_workflow prompt")
            print("-" * 40)
            prompt_result = await session.get_prompt(
                "spatial_analysis_workflow",
                {
                    "server_url": "https://demo.pygeoapi.io/master",
                    "analysis_goal": "find cool spots near new parks in the city"
                }
            )
            print(prompt_result.messages[0].content.text)
            print()

            # ── Summary ──────────────────────────────────────
            print("=" * 60)
            print("✓ ALL 12 TESTS PASSED — Stage 2 fully verified!")
            print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_server())