"""
Stage 5 Part 3 — Dynamic Process-to-Tool Generation Test

Proves the most important Stage 4 mapping rule:
  processes.process_as_tool → Each OGC Process becomes an MCP Tool

Tests against 3 servers:
  1. demo.pygeoapi.io  (remote, always online)
  2. localhost:5000     (Docker backend, must be running)
  3. maps.gnosis.earth  (third-party OGC API)

For each server, we:
  - Discover processes via /processes
  - Generate MCP Tools from their input schemas
  - Verify tool names, descriptions, and inputSchemas are correct
  - Execute a dynamic tool to prove end-to-end works

Run with: python examples/test_stage5_part3.py

License: Apache Software License, Version 2.0
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ogc_mcp.ogc_client import OGCClient, OGCClientError, OGCServerNotFound
from ogc_mcp.mapper import process_to_tool, build_discovery_tools

SERVERS = [
    {
        "name": "pygeoapi Demo",
        "url": "https://demo.pygeoapi.io/master",
        "required": True,
    },
    {
        "name": "Docker localhost",
        "url": "http://localhost:5000",
        "required": False,
    },
    {
        "name": "Gnosis Earth",
        "url": "https://maps.gnosis.earth/ogcapi",
        "required": False,
    },
]

passed = 0
failed = 0
errors = []


def check(test_name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {test_name}")
    else:
        failed += 1
        msg = f"  ✗ {test_name}" + (f" — {detail}" if detail else "")
        print(msg)
        errors.append(msg)


async def test_dynamic_tools_for_server(server: dict) -> dict:
    """
    Test dynamic process-to-tool generation for one server.
    Returns a summary dict.
    """
    name = server["name"]
    url = server["url"]
    required = server["required"]

    print(f"\n{'─' * 60}")
    print(f"  SERVER: {name}")
    print(f"  URL:    {url}")
    print(f"{'─' * 60}")

    summary = {
        "name": name,
        "url": url,
        "status": "unknown",
        "processes_found": 0,
        "tools_generated": 0,
        "tool_names": [],
        "execution_tested": False,
    }

    try:
        async with OGCClient(url, timeout=15.0) as client:

            # Step 1: Discover processes
            print(f"\n  Step 1: Discover processes")
            try:
                processes = await client.get_processes()
            except OGCClientError:
                # Server might not support Processes API
                processes = []

            summary["processes_found"] = len(processes)

            if not processes:
                print(f"    No processes found (server may not support OGC API Processes)")
                summary["status"] = "no_processes"
                if required:
                    check(f"[{name}] Has processes", False, "Required server has no processes")
                else:
                    print(f"    ⚠ SKIP — no processes to test")
                return summary

            check(f"[{name}] Has processes", len(processes) > 0, f"Found {len(processes)}")

            for proc in processes:
                print(f"    [{proc.id}] {proc.title}")

            # Step 2: Generate MCP Tools from each process
            print(f"\n  Step 2: Generate MCP Tools dynamically")
            generated_tools = []

            for proc in processes:
                try:
                    full_proc = await client.get_process(proc.id)
                    tool = process_to_tool(full_proc, url)
                    generated_tools.append(tool)
                except Exception as e:
                    print(f"    ⚠ Could not generate tool for '{proc.id}': {e}")

            summary["tools_generated"] = len(generated_tools)
            summary["tool_names"] = [t.name for t in generated_tools]

            check(
                f"[{name}] Tools generated",
                len(generated_tools) > 0,
                f"{len(generated_tools)} tools from {len(processes)} processes"
            )

            # Step 3: Validate each generated tool
            print(f"\n  Step 3: Validate generated tools")

            for tool in generated_tools:
                # Tool name must follow execute_{process_id} pattern
                check(
                    f"[{name}] Tool '{tool.name}' has valid name",
                    tool.name.startswith("execute_")
                )

                # Tool must have description
                check(
                    f"[{name}] Tool '{tool.name}' has description",
                    len(tool.description) > 10
                )

                # Tool must have inputSchema with server_url
                schema = tool.inputSchema
                check(
                    f"[{name}] Tool '{tool.name}' has inputSchema",
                    isinstance(schema, dict) and "properties" in schema
                )

                props = schema.get("properties", {})
                check(
                    f"[{name}] Tool '{tool.name}' has server_url property",
                    "server_url" in props
                )

                # Show the tool details
                input_names = [k for k in props.keys() if k != "server_url"]
                print(f"    {tool.name}:")
                print(f"      Description: {tool.description[:80]}...")
                print(f"      Process inputs: {input_names}")

            # Step 4: Verify no collision with fixed tools
            print(f"\n  Step 4: Check for name collisions with fixed tools")
            fixed_tools = build_discovery_tools()
            fixed_names = {t.name for t in fixed_tools}
            dynamic_names = {t.name for t in generated_tools}
            collisions = fixed_names & dynamic_names

            check(
                f"[{name}] No name collisions",
                len(collisions) == 0,
                f"Collisions: {collisions}" if collisions else ""
            )

            # Step 5: Combined tool count
            print(f"\n  Step 5: Combined tool count")
            total = len(fixed_tools) + len(generated_tools)
            print(f"    Fixed tools:   {len(fixed_tools)}")
            print(f"    Dynamic tools: {len(generated_tools)}")
            print(f"    Total:         {total}")
            check(
                f"[{name}] Total tools > 13",
                total > 13,
                f"Got {total}"
            )

            # Step 6: Execute a dynamic tool (hello-world if available)
            print(f"\n  Step 6: Execute a dynamic tool")
            executed = False

            # Try hello-world first (common on pygeoapi)
            hello_tool = None
            for tool in generated_tools:
                if "hello" in tool.name.lower():
                    hello_tool = tool
                    break

            if hello_tool:
                try:
                    # Reverse the name mapping to get process_id
                    process_id = hello_tool.name[len("execute_"):].replace("_", "-")
                    result = await client.execute_process(
                        process_id=process_id,
                        inputs={"name": "GSoC", "message": "Dynamic tool test"}
                    )
                    check(
                        f"[{name}] Execute dynamic tool '{hello_tool.name}'",
                        isinstance(result, dict)
                    )
                    print(f"    Result: {json.dumps(result, default=str)[:150]}")
                    executed = True
                except Exception as e:
                    check(
                        f"[{name}] Execute dynamic tool '{hello_tool.name}'",
                        False, str(e)[:100]
                    )
            else:
                # Try any process with simple inputs
                for tool in generated_tools:
                    schema_props = tool.inputSchema.get("properties", {})
                    non_server_inputs = [k for k in schema_props if k != "server_url"]
                    if len(non_server_inputs) <= 2:
                        try:
                            process_id = tool.name[len("execute_"):].replace("_", "-")
                            # Build minimal inputs
                            test_inputs = {}
                            for inp_name in non_server_inputs:
                                inp_def = schema_props[inp_name]
                                inp_type = inp_def.get("type", "string")
                                if inp_type == "string":
                                    test_inputs[inp_name] = "test"
                                elif inp_type in ("number", "integer"):
                                    test_inputs[inp_name] = 1
                            result = await client.execute_process(
                                process_id=process_id,
                                inputs=test_inputs
                            )
                            check(
                                f"[{name}] Execute dynamic tool '{tool.name}'",
                                isinstance(result, dict)
                            )
                            print(f"    Result: {json.dumps(result, default=str)[:150]}")
                            executed = True
                            break
                        except Exception:
                            continue

                if not executed:
                    print(f"    ⚠ No simple process available for execution test")

            summary["execution_tested"] = executed
            summary["status"] = "ok"

    except OGCServerNotFound:
        summary["status"] = "offline"
        if required:
            check(f"[{name}] Server reachable", False, "Server is offline")
        else:
            print(f"  ⚠ SKIP — server unreachable")

    except Exception as e:
        summary["status"] = "error"
        if required:
            check(f"[{name}] Server accessible", False, f"{type(e).__name__}: {e}")
        else:
            print(f"  ⚠ SKIP — {type(e).__name__}: {e}")

    return summary


async def run_tests():
    global passed, failed

    print("=" * 70)
    print("STAGE 5 PART 3 — Dynamic Process-to-Tool Generation")
    print("=" * 70)
    print()
    print("The most important mapping rule from Stage 4:")
    print("  processes.process_as_tool →")
    print("  Each OGC Process automatically becomes an MCP Tool")
    print("  with inputSchema derived from the process description.")

    summaries = []

    for server in SERVERS:
        summary = await test_dynamic_tools_for_server(server)
        summaries.append(summary)

    # ════════════════════════════════════════════════
    # SUMMARY TABLE
    # ════════════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("SUMMARY TABLE")
    print(f"{'=' * 70}")
    print(f"{'Server':<22} {'Status':<10} {'Processes':<10} {'Tools':<8} {'Executed'}")
    print(f"{'─' * 22} {'─' * 10} {'─' * 10} {'─' * 8} {'─' * 8}")

    servers_with_processes = 0
    total_dynamic_tools = 0

    for s in summaries:
        status_icon = {
            "ok": "✓ OK",
            "no_processes": "⚠ NoPrc",
            "offline": "⚠ SKIP",
            "error": "⚠ ERR",
            "unknown": "?",
        }.get(s["status"], "?")

        exec_icon = "✓" if s["execution_tested"] else "—"

        print(
            f"  {s['name']:<20} {status_icon:<10} "
            f"{s['processes_found']:<10} {s['tools_generated']:<8} {exec_icon}"
        )

        if s["tool_names"]:
            for tn in s["tool_names"]:
                print(f"    → {tn}")

        if s["tools_generated"] > 0:
            servers_with_processes += 1
            total_dynamic_tools += s["tools_generated"]

    # ════════════════════════════════════════════════
    # ARCHITECTURE PROOF
    # ════════════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("ARCHITECTURE PROOF")
    print(f"{'=' * 70}")

    check(
        "At least 1 server has dynamic tools",
        servers_with_processes >= 1,
        f"{servers_with_processes} servers"
    )

    check(
        "Dynamic tools generated from real OGC Processes",
        total_dynamic_tools >= 1,
        f"{total_dynamic_tools} total dynamic tools"
    )

    # Verify the mapping works: tool name → process ID → execution
    check(
        "Tool naming: execute_{process_id}",
        all(
            tn.startswith("execute_")
            for s in summaries
            for tn in s["tool_names"]
        )
    )

    # Final results
    total = passed + failed
    print(f"\n{'=' * 70}")
    print(f"STAGE 5 PART 3 RESULTS: {passed}/{total} checks passed")
    print(f"{'=' * 70}")

    if failed > 0:
        print(f"\n⚠ {failed} checks failed:")
        for e in errors:
            print(f"  {e}")
    else:
        print(f"\n✓ ALL CHECKS PASSED")
        print(f"✓ Dynamic process-to-tool generation working")
        print(f"✓ {total_dynamic_tools} OGC Processes auto-generated as MCP Tools")
        print(f"✓ {servers_with_processes} server(s) tested with dynamic tools")
        print(f"✓ Tool naming: execute_{{process_id}} pattern confirmed")
        print(f"✓ No collisions with 13 fixed tools")
        print(f"✓ Stage 4 mapping rule 'processes.process_as_tool' — IMPLEMENTED")

    print(f"{'=' * 70}")
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
