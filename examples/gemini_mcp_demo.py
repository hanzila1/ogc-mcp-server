"""
Stage 6 — Gemini LLM + OGC API Demo
GSoC 2026: MCP for OGC APIs — 52°North

Natural language → Gemini function calling → OGCClient → OGC API servers

5 Demo Scenarios:
  1. Server Discovery   — What data is available?
  2. Feature Query      — Show me lakes in Europe
  3. Cool Spot Analysis — The exact 52North project scenario (Münster parks)
  4. Catalog Search     — Find water datasets in Dutch metadata
  5. Environmental Data — Sea surface temperature (EDR)

Usage:
  python examples/gemini_mcp_demo.py        # Run all 5 scenarios
  python examples/gemini_mcp_demo.py chat   # Interactive chat mode

Requirements:
  pip install google-genai python-dotenv

License: Apache Software License, Version 2.0
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY not found in .env")
    print("Add it: GEMINI_API_KEY=your_key_here")
    print("Get one free: https://aistudio.google.com/apikey")
    sys.exit(1)

from google import genai
from google.genai import types
from ogc_mcp.ogc_client import OGCClient

client = genai.Client(api_key=GEMINI_API_KEY)

GEMINI_MODEL = "gemini-2.5-flash"
DEMO_SERVER  = "https://demo.pygeoapi.io/master"
LOCAL_SERVER = "http://localhost:5000"

SYSTEM_INSTRUCTION = """You are a geospatial analytics assistant helping non-experts
interact with OGC API geospatial services through natural language.

You have tools connecting to OGC API servers worldwide. You can:
- Discover what data and services any OGC server offers
- Query geographic features with spatial and temporal filters
- Search metadata catalogs for geospatial datasets
- Retrieve environmental data at any location
- Execute geospatial analysis processes

When a user asks a geospatial question:
1. Choose the right tool
2. Call it with correct parameters
3. Present results in plain non-technical language

Be concise. The user is a non-expert who wants answers, not GIS jargon."""

OGC_TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="discover_ogc_server",
        description="Discover what data and capabilities an OGC API server offers.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"server_url": types.Schema(type=types.Type.STRING, description="URL of the OGC API server")},
            required=["server_url"]
        )
    ),
    types.FunctionDeclaration(
        name="get_collections",
        description="List all data collections on an OGC server.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"server_url": types.Schema(type=types.Type.STRING, description="URL of the OGC API server")},
            required=["server_url"]
        )
    ),
    types.FunctionDeclaration(
        name="get_features",
        description="Retrieve geographic features from a collection. Can filter by bounding box.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "server_url": types.Schema(type=types.Type.STRING, description="URL of the OGC API server"),
                "collection_id": types.Schema(type=types.Type.STRING, description="Collection ID e.g. lakes, parks"),
                "limit": types.Schema(type=types.Type.INTEGER, description="Max features to return"),
                "bbox": types.Schema(type=types.Type.STRING, description="Bounding box: minLon,minLat,maxLon,maxLat"),
            },
            required=["server_url", "collection_id"]
        )
    ),
    types.FunctionDeclaration(
        name="discover_processes",
        description="List all geospatial analysis processes available on an OGC server.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"server_url": types.Schema(type=types.Type.STRING, description="URL of the OGC API server")},
            required=["server_url"]
        )
    ),
    types.FunctionDeclaration(
        name="execute_process",
        description="Execute a geospatial analysis process with given inputs.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "server_url": types.Schema(type=types.Type.STRING, description="URL of the OGC API server"),
                "process_id": types.Schema(type=types.Type.STRING, description="Process ID e.g. cool-spot-demo"),
                "inputs_json": types.Schema(type=types.Type.STRING, description="Process inputs as JSON string"),
            },
            required=["server_url", "process_id", "inputs_json"]
        )
    ),
    types.FunctionDeclaration(
        name="search_catalog",
        description="Search an OGC Records catalog for geospatial datasets by keyword.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "server_url": types.Schema(type=types.Type.STRING, description="URL of the OGC API server"),
                "collection_id": types.Schema(type=types.Type.STRING, description="Catalog collection ID"),
                "q": types.Schema(type=types.Type.STRING, description="Search keyword"),
                "limit": types.Schema(type=types.Type.INTEGER, description="Max results"),
            },
            required=["server_url", "collection_id"]
        )
    ),
    types.FunctionDeclaration(
        name="query_edr_position",
        description="Query environmental or climate data at a specific geographic point.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "server_url": types.Schema(type=types.Type.STRING, description="URL of the OGC API server"),
                "collection_id": types.Schema(type=types.Type.STRING, description="EDR collection ID"),
                "coords": types.Schema(type=types.Type.STRING, description="Point in WKT: POINT(lon lat)"),
                "parameter_name": types.Schema(type=types.Type.STRING, description="Parameter e.g. SST"),
            },
            required=["server_url", "collection_id", "coords"]
        )
    ),
])


async def execute_tool(tool_name: str, tool_args: dict) -> str:
    server_url = tool_args.get("server_url", DEMO_SERVER)
    try:
        async with OGCClient(server_url) as ogc:

            if tool_name == "discover_ogc_server":
                info = await ogc.get_server_info()
                cols = await ogc.get_collections()
                r = f"Server: {info.title}\nDescription: {info.description}\n"
                r += f"Capabilities: {', '.join(info.capabilities)}\n"
                r += f"Collections ({len(cols)} total):\n"
                for c in cols[:8]:
                    r += f"  [{c.id}] {c.title}\n"
                if len(cols) > 8:
                    r += f"  ... and {len(cols)-8} more\n"
                return r

            elif tool_name == "get_collections":
                cols = await ogc.get_collections()
                r = f"Found {len(cols)} collections:\n"
                for c in cols:
                    r += f"  [{c.id}] {c.title}"
                    if c.description:
                        r += f" — {c.description[:60]}"
                    r += "\n"
                return r

            elif tool_name == "get_features":
                data = await ogc.get_features(
                    collection_id=tool_args.get("collection_id"),
                    limit=tool_args.get("limit", 10),
                    bbox=tool_args.get("bbox")
                )
                features = data.get("features", [])
                total = data.get("numberMatched", len(features))
                r = f"Retrieved {len(features)} of {total} features"
                if tool_args.get("bbox"):
                    r += f" (bbox: {tool_args['bbox']})"
                r += ":\n\n"
                for i, f in enumerate(features, 1):
                    props = f.get("properties", {})
                    name = props.get("name") or props.get("title") or f.get("id", f"Feature {i}")
                    geom_type = f.get("geometry", {}).get("type", "")
                    r += f"{i}. {name}"
                    if geom_type:
                        r += f" ({geom_type})"
                    r += "\n"
                    for k, v in list(props.items())[:3]:
                        if k not in ("name", "title") and v:
                            r += f"   {k}: {v}\n"
                return r

            elif tool_name == "discover_processes":
                procs = await ogc.get_processes()
                r = f"Found {len(procs)} processes:\n"
                for p in procs:
                    r += f"  [{p.id}] {p.title}\n"
                    if p.description:
                        r += f"    {p.description[:80]}\n"
                return r

            elif tool_name == "execute_process":
                inputs_json = tool_args.get("inputs_json", "{}")
                try:
                    inputs = json.loads(inputs_json)
                except json.JSONDecodeError:
                    inputs = {}
                process_id = tool_args.get("process_id")
                output = await ogc.execute_process(
                    process_id=process_id,
                    inputs=inputs,
                    async_execute=False
                )
                return f"Process '{process_id}' completed.\nResult:\n{json.dumps(output, indent=2, ensure_ascii=False)[:3000]}"

            elif tool_name == "search_catalog":
                results = await ogc.search_records(
                    collection_id=tool_args.get("collection_id"),
                    q=tool_args.get("q"),
                    limit=tool_args.get("limit", 5)
                )
                features = results.get("features", [])
                total = results.get("numberMatched", len(features))
                r = f"Found {total} records"
                if tool_args.get("q"):
                    r += f" matching '{tool_args['q']}'"
                r += f" (showing {len(features)}):\n\n"
                for i, f in enumerate(features, 1):
                    title = f.get("properties", {}).get("title", "Untitled")
                    desc = f.get("properties", {}).get("description", "")
                    r += f"{i}. {title}\n"
                    if desc:
                        r += f"   {desc[:100]}\n"
                return r

            elif tool_name == "query_edr_position":
                data = await ogc.query_edr_position(
                    collection_id=tool_args.get("collection_id"),
                    coords=tool_args.get("coords"),
                    parameter_name=tool_args.get("parameter_name")
                )
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except Exception:
                        return data
                ranges = data.get("ranges", {})
                r = f"Environmental data at {tool_args.get('coords')}:\n"
                for param_id, param_data in ranges.items():
                    values = param_data.get("values", [])
                    unit = param_data.get("unit", {})
                    unit_label = unit.get("label", {})
                    unit_str = unit_label.get("en", "") if isinstance(unit_label, dict) else str(unit_label)
                    numeric = [v for v in values if v is not None]
                    if numeric:
                        avg = sum(numeric) / len(numeric)
                        r += f"  {param_id}: avg={avg:.2f} {unit_str}, min={min(numeric):.2f}, max={max(numeric):.2f}\n"
                return r

            else:
                return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def run_conversation(user_message: str, show_tools: bool = True) -> str:
    loop = asyncio.get_event_loop()

    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    ]

    for turn in range(6):
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[OGC_TOOLS],
                temperature=0.1,
            )
        )

        function_calls = response.function_calls
        if not function_calls:
            return response.text or "No response."

        contents.append(response.candidates[0].content)

        tool_response_parts = []
        for fc in function_calls:
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}

            if show_tools:
                args_preview = ", ".join(
                    f"{k}={repr(str(v))[:40]}" for k, v in tool_args.items()
                )
                print(f"    → {tool_name}({args_preview})")

            result = loop.run_until_complete(execute_tool(tool_name, tool_args))

            tool_response_parts.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"result": result[:4000]}
                )
            )

        contents.append(
            types.Content(role="tool", parts=tool_response_parts)
        )

    return "Max turns reached."


DEMO_SCENARIOS = [
    {
        "title": "1. Server Discovery",
        "context": "Non-expert discovering what a server offers",
        "message": f"What geospatial data and services are available at {DEMO_SERVER}?"
    },
    {
        "title": "2. Feature Query — Lakes in Europe",
        "context": "Spatial query with bounding box filter",
        "message": f"Show me lakes in Europe from {DEMO_SERVER}. Use bbox -10,35,40,75 to filter by Europe."
    },
    {
        "title": "3. Cool Spot Analysis — The GSoC Scenario",
        "context": "Urban planner in Münster — exact 52North project description scenario",
        "message": (
            f"I am an urban planner in Münster. Run a cool spot analysis on my parks "
            f"using server {LOCAL_SERVER} and process cool-spot-demo. "
            f'Use these inputs as JSON: {{"park_geometries": {{"type": "FeatureCollection", '
            f'"features": [{{"type": "Feature", "properties": {{"name": "Aasee Park", '
            f'"area_ha": 52.3, "tree_coverage": 0.45, "has_water": true}}, "geometry": '
            f'{{"type": "Polygon", "coordinates": [[[7.607,51.949],[7.617,51.949],'
            f'[7.617,51.957],[7.607,51.957],[7.607,51.949]]]}}}}, '
            f'{{"type": "Feature", "properties": {{"name": "Schlosspark", "area_ha": 18.7, '
            f'"tree_coverage": 0.80, "has_water": false}}, "geometry": {{"type": "Polygon", '
            f'"coordinates": [[[7.612,51.962],[7.622,51.962],[7.622,51.968],'
            f'[7.612,51.968],[7.612,51.962]]]}}}}]}}, "buffer_km": 0.5, "city_name": "Munster"}}. '
            f"Which park creates better cooling?"
        )
    },
    {
        "title": "4. Catalog Search — Records API",
        "context": "Searching metadata catalog for datasets",
        "message": f"Search the dutch-metadata catalog at {DEMO_SERVER} for datasets about water."
    },
    {
        "title": "5. Environmental Data — Sea Surface Temperature",
        "context": "OGC API EDR — real oceanographic data",
        "message": f"What is the sea surface temperature at longitude 33, latitude 33? Use collection icoads-sst at {DEMO_SERVER}."
    }
]


def run_all_scenarios():
    print("=" * 70)
    print("STAGE 6 — Gemini LLM + OGC API Demo")
    print("GSoC 2026: MCP for OGC APIs @ 52°North")
    print("=" * 70)
    print(f"  Model:   {GEMINI_MODEL}")
    print(f"  SDK:     google-genai (new, not deprecated)")
    print(f"  Servers: demo.pygeoapi.io + localhost:5000")
    print()
    print("Architecture:")
    print("  User → Gemini (intent + tool selection) → OGCClient → OGC API")
    print()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    passed = 0
    failed = 0

    for scenario in DEMO_SCENARIOS:
        print("─" * 70)
        print(f"  SCENARIO: {scenario['title']}")
        print(f"  Context:  {scenario['context']}")
        print("─" * 70)
        print(f"\n  User: {scenario['message'][:120]}...")
        print()
        print("  [Gemini selecting and calling tools...]")
        print()

        try:
            answer = run_conversation(scenario["message"])
            print(f"  Gemini: {answer}")
            passed += 1
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

        print()

    loop.close()

    print("=" * 70)
    print(f"Results: {passed}/{passed+failed} scenarios completed")
    if failed == 0:
        print("✓ All scenarios passed")
        print("✓ Natural language → OGC API → plain language answers")
        print("✓ Stage 6 complete — GSoC 2026 MCP for OGC APIs")
    print("=" * 70)


def run_interactive_chat():
    print("=" * 70)
    print("Gemini + OGC API — Interactive Chat")
    print("=" * 70)
    print(f"  Model: {GEMINI_MODEL}")
    print(f"  Servers: {DEMO_SERVER}")
    print(f"           {LOCAL_SERVER}")
    print()
    print("  Ask anything geospatial. Type 'quit' to exit.")
    print("=" * 70)
    print()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        print()
        try:
            answer = run_conversation(user_input)
            print(f"Gemini: {answer}")
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")
        print()

    loop.close()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if mode == "chat":
        run_interactive_chat()
    else:
        run_all_scenarios()
