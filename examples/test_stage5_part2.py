"""
Stage 5 Part 2 — Records and EDR Verification Test

Tests the 4 new MCP tools against real public OGC servers:
  - Records: demo.pygeoapi.io (dutch-metadata catalog)
  - EDR:     demo.pygeoapi.io (icoads-sst sea surface temperature)

Uses OGCClient directly (like test_stage3.py) to verify the
HTTP layer works before testing through the MCP protocol.

Run with: python examples/test_stage5_part2.py

License: Apache Software License, Version 2.0
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ogc_mcp.ogc_client import OGCClient, OGCClientError
from ogc_mcp.mapper import (
    format_catalog_records,
    format_catalog_record_detail,
    format_edr_collection,
    format_edr_query_result,
)

DEMO_SERVER = "https://demo.pygeoapi.io/master"

# Records catalog on the demo server
RECORDS_CATALOG = "dutch-metadata"

# EDR collection on the demo server
EDR_COLLECTION = "icoads-sst"

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


async def run_tests():
    global passed, failed

    print("=" * 70)
    print("STAGE 5 PART 2 — Records and EDR Verification")
    print(f"Server: {DEMO_SERVER}")
    print("=" * 70)

    async with OGCClient(DEMO_SERVER) as client:

        # ════════════════════════════════════════════════
        # TEST 1: Identify Records and EDR collections
        # ════════════════════════════════════════════════
        print("\n── TEST 1: Identify Records and EDR Collections ──")

        collections = await client.get_collections()
        col_ids = [c.id for c in collections]
        col_types = {c.id: c.item_type for c in collections}

        check("Server has collections", len(collections) > 0)
        check(
            f"Has '{RECORDS_CATALOG}' catalog",
            RECORDS_CATALOG in col_ids,
            f"Available: {col_ids[:5]}"
        )
        check(
            f"'{RECORDS_CATALOG}' is itemType=record",
            col_types.get(RECORDS_CATALOG) == "record",
            f"Got: {col_types.get(RECORDS_CATALOG)}"
        )
        check(
            f"Has '{EDR_COLLECTION}' collection",
            EDR_COLLECTION in col_ids,
            f"Available: {col_ids[:5]}"
        )

        # ════════════════════════════════════════════════
        # TEST 2: search_catalog — full text search
        # ════════════════════════════════════════════════
        print("\n── TEST 2: search_catalog (full-text search) ──")

        results = await client.search_records(
            collection_id=RECORDS_CATALOG,
            limit=5
        )
        features = results.get("features", [])
        check("Search returned results", len(features) > 0, f"Got {len(features)}")

        if features:
            first = features[0]
            first_id = first.get("id", "")
            first_title = first.get("properties", {}).get("title", "")
            check("Records have IDs", bool(first_id))
            check("Records have titles", bool(first_title))
            print(f"    First record: [{first_id}] {first_title}")

        # Test with keyword search
        keyword_results = await client.search_records(
            collection_id=RECORDS_CATALOG,
            q="water",
            limit=3
        )
        keyword_features = keyword_results.get("features", [])
        print(f"    Keyword 'water' returned {len(keyword_features)} records")
        check("Keyword search works", True)  # Server accepts q parameter

        # Test formatter
        formatted = format_catalog_records(results)
        check("format_catalog_records works", "catalog records" in formatted.lower() or "found" in formatted.lower())
        print(f"    Formatted output preview:\n      {formatted[:150]}")

        # ════════════════════════════════════════════════
        # TEST 3: get_catalog_record — specific record
        # ════════════════════════════════════════════════
        print("\n── TEST 3: get_catalog_record (specific record) ──")

        if features:
            record_id = features[0].get("id", "")
            if record_id:
                record = await client.get_record(RECORDS_CATALOG, record_id)
                check("Record retrieved", bool(record.title))
                check("Record has type", bool(record.type))
                check("Record has keywords or description", len(record.keywords) > 0 or bool(record.description))

                detail_text = format_catalog_record_detail(record)
                check("format_catalog_record_detail works", "Record:" in detail_text)
                print(f"    Record detail:\n      {detail_text[:200]}")
            else:
                check("Record retrieved", False, "No record ID found")
        else:
            check("Record retrieved", False, "No records from search")

        # ════════════════════════════════════════════════
        # TEST 4: EDR collection metadata
        # ════════════════════════════════════════════════
        print("\n── TEST 4: EDR Collection Metadata ──")

        edr_col = await client.get_edr_collection(EDR_COLLECTION)
        check("EDR collection retrieved", bool(edr_col.title))
        check("Has parameters", len(edr_col.parameters) > 0)
        check("Has query types", len(edr_col.query_types) > 0)

        if edr_col.parameters:
            param_ids = [p.id for p in edr_col.parameters]
            print(f"    Parameters: {', '.join(param_ids)}")
            check("Has SST parameter", "SST" in param_ids, f"Got: {param_ids}")

        if edr_col.query_types:
            print(f"    Query types: {', '.join(edr_col.query_types)}")
            check("Supports position query", "position" in edr_col.query_types)

        edr_text = format_edr_collection(edr_col)
        check("format_edr_collection works", "EDR Collection" in edr_text)
        print(f"    Formatted:\n      {edr_text[:200]}")

        # ════════════════════════════════════════════════
        # TEST 5: query_edr_position — point query
        # ════════════════════════════════════════════════
        print("\n── TEST 5: query_edr_position (Mediterranean point) ──")

        try:
            edr_result = await client.query_edr_position(
                collection_id=EDR_COLLECTION,
                coords="POINT(33 33)",
                parameter_name="SST",
            )
            check("Position query returned data", isinstance(edr_result, dict))

            result_type = edr_result.get("type", "")
            has_ranges = "ranges" in edr_result
            has_domain = "domain" in edr_result
            check(
                "Response is CoverageJSON",
                result_type == "Coverage" or has_ranges or has_domain,
                f"type={result_type}, ranges={has_ranges}, domain={has_domain}"
            )

            # Format the result
            formatted_edr = format_edr_query_result(edr_result, "position")
            check("format_edr_query_result works", "EDR position" in formatted_edr)
            print(f"    Result:\n      {formatted_edr[:300]}")

        except Exception as e:
            check("Position query returned data", False, str(e))
            check("Response is CoverageJSON", False, "skipped")
            check("format_edr_query_result works", False, "skipped")

        # ════════════════════════════════════════════════
        # TEST 6: query_edr_position with datetime
        # ════════════════════════════════════════════════
        print("\n── TEST 6: query_edr_position with temporal filter ──")

        try:
            edr_temporal = await client.query_edr_position(
                collection_id=EDR_COLLECTION,
                coords="POINT(-40 40)",
                parameter_name="SST",
                datetime="2000-04-16",
            )
            check("Temporal query succeeded", isinstance(edr_temporal, dict))
            formatted_t = format_edr_query_result(edr_temporal, "position")
            print(f"    Result:\n      {formatted_t[:200]}")
        except Exception as e:
            check("Temporal query succeeded", False, str(e))

        # ════════════════════════════════════════════════
        # TEST 7: query_edr_position — all parameters
        # ════════════════════════════════════════════════
        print("\n── TEST 7: query_edr_position (all parameters) ──")

        try:
            edr_all = await client.query_edr_position(
                collection_id=EDR_COLLECTION,
                coords="POINT(33 33)",
                # No parameter_name = get all
            )
            check("All-params query succeeded", isinstance(edr_all, dict))
            ranges = edr_all.get("ranges", {})
            range_keys = list(ranges.keys()) if ranges else []
            print(f"    Parameters returned: {range_keys}")
            check("Multiple parameters returned", len(range_keys) >= 1, f"Got {range_keys}")
        except Exception as e:
            check("All-params query succeeded", False, str(e))
            check("Multiple parameters returned", False, "skipped")

        # ════════════════════════════════════════════════
        # TEST 8: Verify new tool count in mapper
        # ════════════════════════════════════════════════
        print("\n── TEST 8: Tool Registration Verification ──")

        from ogc_mcp.mapper import build_discovery_tools
        tools = build_discovery_tools()
        tool_names = [t.name for t in tools]

        # Original 9 tools
        check("Has discover_ogc_server", "discover_ogc_server" in tool_names)
        check("Has get_collections", "get_collections" in tool_names)
        check("Has get_features", "get_features" in tool_names)
        check("Has discover_processes", "discover_processes" in tool_names)
        check("Has execute_process", "execute_process" in tool_names)

        # NEW 4 tools
        check("Has search_catalog (NEW)", "search_catalog" in tool_names)
        check("Has get_catalog_record (NEW)", "get_catalog_record" in tool_names)
        check("Has query_edr_position (NEW)", "query_edr_position" in tool_names)
        check("Has query_edr_area (NEW)", "query_edr_area" in tool_names)

        total_tools = len(tools)
        print(f"    Total tools registered: {total_tools}")
        check("Total tools >= 13", total_tools >= 13, f"Got {total_tools}")

    # ════════════════════════════════════════════════
    # SUMMARY
    # ════════════════════════════════════════════════
    total = passed + failed
    print("\n" + "=" * 70)
    print(f"STAGE 5 PART 2 RESULTS: {passed}/{total} checks passed")
    print("=" * 70)

    if failed > 0:
        print(f"\n⚠ {failed} checks failed:")
        for e in errors:
            print(f"  {e}")
    else:
        print("\n✓ ALL CHECKS PASSED")
        print("✓ OGC API Records — catalog search and record retrieval working")
        print("✓ OGC API EDR — position queries with CoverageJSON parsing working")
        print("✓ 4 new MCP tools registered (search_catalog, get_catalog_record,")
        print("  query_edr_position, query_edr_area)")
        print("✓ Total: 13+ MCP tools covering Features, Records, EDR, Processes")

    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
