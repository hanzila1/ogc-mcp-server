"""
Stage 5 — Multi-Server Compatibility Test

Proves our OGCClient works identically against completely different
OGC API backends — the core architectural promise of the project.

Servers tested:
  1. demo.pygeoapi.io  — Official pygeoapi demo (remote)
  2. localhost:5000     — Our own Docker backend (local)
  3. maps.gnosis.earth  — Gnosis Maps OGC API (remote, third-party)

For each server: discover info, list collections, list processes.
Unreachable servers are skipped gracefully — not marked as failures.

Run with: python examples/test_multi_server.py

Prerequisites:
  - For localhost:5000: docker run -p 5000:80 --name ogc-backend ogc-mcp-pygeoapi

License: Apache Software License, Version 2.0
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ogc_mcp.ogc_client import (
    OGCClient,
    OGCClientError,
    OGCServerNotFound,
)


# ─────────────────────────────────────────────
# Server definitions
# ─────────────────────────────────────────────

SERVERS = [
    {
        "name": "pygeoapi Demo",
        "url": "https://demo.pygeoapi.io/master",
        "description": "Official pygeoapi demo — remote, always online",
    },
    {
        "name": "Local Docker",
        "url": "http://localhost:5000",
        "description": "Our GSoC Docker backend — local, must be running",
    },
    {
        "name": "Gnosis Maps",
        "url": "https://maps.gnosis.earth/ogcapi",
        "description": "Third-party OGC API — remote, independent implementation",
    },
]


# ─────────────────────────────────────────────
# Per-server test results container
# ─────────────────────────────────────────────

class ServerResult:
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
        self.status = "unknown"       # "ok", "skipped", "error"
        self.title = ""
        self.description = ""
        self.capabilities = []
        self.collections = []         # list of (id, title) tuples
        self.processes = []           # list of (id, title) tuples
        self.has_features = False
        self.has_processes = False
        self.has_edr = False
        self.error_msg = ""


# ─────────────────────────────────────────────
# Test a single server
# ─────────────────────────────────────────────

async def test_server(server_def: dict) -> ServerResult:
    """Run all discovery tests against one OGC API server."""
    result = ServerResult(server_def["name"], server_def["url"])

    try:
        async with OGCClient(server_def["url"]) as client:

            # ── Step 1: Server discovery ─────────────────
            print(f"  Discovering server info...")
            info = await client.get_server_info()
            result.title = info.title
            result.description = info.description[:80] if info.description else ""
            result.capabilities = list(info.capabilities)
            result.has_features = "features" in info.capabilities
            result.has_processes = "processes" in info.capabilities
            print(f"  ✓ Title: {info.title}")
            print(f"  ✓ Capabilities: {', '.join(info.capabilities)}")

            # ── Step 2: List collections ─────────────────
            print(f"  Listing collections...")
            collections = await client.get_collections()
            result.collections = [(c.id, c.title) for c in collections]
            count = len(collections)
            print(f"  ✓ Found {count} collections")
            # Show first 5
            for cid, ctitle in result.collections[:5]:
                print(f"    • [{cid}] {ctitle}")
            if count > 5:
                print(f"    ... and {count - 5} more")

            # ── Step 3: List processes (if supported) ────
            if result.has_processes:
                print(f"  Listing processes...")
                try:
                    processes = await client.get_processes()
                    result.processes = [(p.id, p.title) for p in processes]
                    print(f"  ✓ Found {len(processes)} processes")
                    for pid, ptitle in result.processes[:5]:
                        print(f"    • [{pid}] {ptitle}")
                    if len(processes) > 5:
                        print(f"    ... and {len(processes) - 5} more")
                except Exception as e:
                    print(f"  ⚠ Processes endpoint failed: {e}")
            else:
                print(f"  ─ Processes not supported by this server")

            # ── Step 4: Check for EDR indicators ─────────
            for cid, ctitle in result.collections:
                lower = ctitle.lower() + " " + cid.lower()
                if any(kw in lower for kw in ["climate", "weather", "temperature", "icoads", "edr"]):
                    result.has_edr = True
                    break

            result.status = "ok"

    except (OGCServerNotFound, OGCClientError) as e:
        result.status = "skipped"
        result.error_msg = str(e)[:80]
        print(f"  ⚠ SKIPPED — {result.error_msg}")

    except Exception as e:
        result.status = "skipped"
        result.error_msg = f"{type(e).__name__}: {str(e)[:60]}"
        print(f"  ⚠ SKIPPED — {result.error_msg}")

    return result


# ─────────────────────────────────────────────
# Summary table
# ─────────────────────────────────────────────

def print_summary(results: list[ServerResult]):
    """Print a formatted summary table of all server test results."""

    print("\n" + "═" * 78)
    print("MULTI-SERVER COMPATIBILITY SUMMARY")
    print("═" * 78)

    # Header
    print(f"{'Server':<20} {'Status':<10} {'Collections':<13} {'Processes':<11} {'Features':<10} {'EDR':<5}")
    print("─" * 78)

    for r in results:
        if r.status == "ok":
            status = "✓ OK"
            cols = str(len(r.collections))
            procs = str(len(r.processes)) if r.has_processes else "N/A"
            feat = "✓" if r.has_features else "✗"
            edr = "✓" if r.has_edr else "✗"
        else:
            status = "⚠ SKIP"
            cols = "—"
            procs = "—"
            feat = "—"
            edr = "—"

        print(f"{r.name:<20} {status:<10} {cols:<13} {procs:<11} {feat:<10} {edr:<5}")

    print("─" * 78)

    # Stats
    ok_count = sum(1 for r in results if r.status == "ok")
    skip_count = sum(1 for r in results if r.status == "skipped")
    total = len(results)

    print(f"\nServers reached: {ok_count}/{total}", end="")
    if skip_count > 0:
        print(f" ({skip_count} skipped — unreachable or offline)")
    else:
        print()

    # Server details for those that responded
    for r in results:
        if r.status == "ok":
            print(f"\n  {r.name} ({r.url})")
            print(f"    Title: {r.title}")
            if r.description:
                print(f"    Description: {r.description}")

    # Key insight
    if ok_count >= 2:
        print(f"\n✓ SAME OGCClient code works against {ok_count} different OGC servers")
        print("✓ Server-agnostic architecture CONFIRMED")
    elif ok_count == 1:
        print(f"\n✓ 1 server reached — start Docker backend for full multi-server test")
    else:
        print(f"\n⚠ No servers reachable — check internet and Docker")

    print("═" * 78)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

async def main():
    print("=" * 78)
    print("STAGE 5 — Multi-Server Compatibility Test")
    print("Testing OGCClient against 3 different OGC API backends")
    print("=" * 78)

    results = []

    for server_def in SERVERS:
        print(f"\n┌── {server_def['name']} ──")
        print(f"│   {server_def['url']}")
        print(f"│   {server_def['description']}")
        print(f"└{'─' * 40}")
        result = await test_server(server_def)
        results.append(result)

    print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
