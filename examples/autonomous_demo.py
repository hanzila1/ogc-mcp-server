"""
Autonomous Geospatial Assistant
GSoC 2026: MCP for OGC APIs — 52°North

The user just asks questions in plain English.
The system figures out EVERYTHING automatically:
  - Which server to use
  - What data is available
  - Which tool to call
  - How to interpret results

NO server URLs needed. NO technical knowledge needed.
Just ask.

Known OGC servers the system can autonomously explore:
  - demo.pygeoapi.io       → Netherlands data, ocean/climate EDR, metadata
  - maps.gnosis.earth      → Global elevation, terrain, routing, NaturalEarth
  - localhost:5000          → Münster parks, cool spot, buffer analysis

Usage:
  python examples/autonomous_demo.py         # interactive chat
  python examples/autonomous_demo.py demo    # run showcase scenarios

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
    sys.exit(1)

from google import genai
from google.genai import types
from ogc_mcp.ogc_client import OGCClient

client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-2.5-flash"

# ─────────────────────────────────────────────────────────────────
# THE KEY — System prompt that teaches autonomous discovery
# ─────────────────────────────────────────────────────────────────

AUTONOMOUS_SYSTEM_PROMPT = """You are an intelligent geospatial assistant. 
You help anyone — experts or complete beginners — understand and analyze the world through geospatial data.

You have access to MULTIPLE real OGC API servers. You decide which one to use based on the question.

KNOWN SERVERS AND WHAT THEY CONTAIN:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. https://demo.pygeoapi.io/master
   → Dutch windmills, castles, lakes (global)
   → Ocean & climate data (sea temperature, wind) via EDR
   → Dutch metadata catalog (309 datasets, historical records)
   → Hydrological observations, airports, populated places
   → Use for: Netherlands data, European features, ocean conditions, metadata search

2. https://maps.gnosis.earth/ogcapi  
   → 749 collections including NaturalEarth global data
   → Elevation and terrain analysis processes
   → Countries, rivers, cities worldwide (NaturalEarth)
   → Point cloud, routing, classification processes
   → Use for: ANY country/location worldwide, elevation, terrain, global features

3. http://localhost:5000
   → Münster Germany parks (Central Park 341ha, Aasee 52ha, Schlosspark 18ha)
   → Cool spot analysis process (urban heat island)
   → Geospatial buffer process
   → Use for: Münster urban analysis, park cooling, city planning

AUTONOMOUS DISCOVERY RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. NEVER ask the user for a server URL — you know the servers
2. NEVER ask for technical parameters — figure them out yourself
3. For ANY location question → use gnosis.earth (749 global collections)
4. For Netherlands/Dutch data → use pygeoapi demo
5. For ocean/climate data → use pygeoapi demo EDR collections
6. For Münster parks/urban → use localhost:5000
7. When unsure → call list_known_servers first, then explore

DISCOVERY CHAIN (follow this for unknown requests):
  Step 1: pick the best server based on the question
  Step 2: call discover_server to see what it offers
  Step 3: call list_collections to find relevant data
  Step 4: query or analyze the data
  Step 5: explain results in plain language

ANALYSIS APPROACH:
  - For location questions: find features, describe what's there
  - For environmental questions: use EDR for measurements
  - For urban planning: use processes for spatial analysis
  - For historical/metadata: search records catalogs
  - Always give practical, human-meaningful answers
  - Tell the user what you found AND what it means for them

You are the bridge between complex geospatial data and human understanding.
Make data accessible to EVERYONE."""


# ─────────────────────────────────────────────────────────────────
# Tool Definitions
# ─────────────────────────────────────────────────────────────────

TOOLS = types.Tool(function_declarations=[

    types.FunctionDeclaration(
        name="list_known_servers",
        description="List all known OGC API servers and what data they contain. Call this when unsure which server to use.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={})
    ),

    types.FunctionDeclaration(
        name="discover_server",
        description="Explore an OGC server to understand what it offers — title, capabilities, number of collections.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"server_url": types.Schema(type=types.Type.STRING, description="Server URL to explore")},
            required=["server_url"]
        )
    ),

    types.FunctionDeclaration(
        name="list_collections",
        description="List all data collections on a server. Use this to find what datasets are available.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"server_url": types.Schema(type=types.Type.STRING, description="Server URL")},
            required=["server_url"]
        )
    ),

    types.FunctionDeclaration(
        name="find_collection",
        description="Search a server's collections by keyword to find the most relevant dataset for a question.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "server_url": types.Schema(type=types.Type.STRING, description="Server URL"),
                "keyword": types.Schema(type=types.Type.STRING, description="What to search for e.g. 'lakes', 'temperature', 'elevation'"),
            },
            required=["server_url", "keyword"]
        )
    ),

    types.FunctionDeclaration(
        name="get_features",
        description="Get geographic features from a collection. Optionally filter by area (bbox) or limit count.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "server_url": types.Schema(type=types.Type.STRING),
                "collection_id": types.Schema(type=types.Type.STRING, description="Collection ID to query"),
                "limit": types.Schema(type=types.Type.INTEGER, description="Max features, default 10"),
                "bbox": types.Schema(type=types.Type.STRING, description="Area filter: minLon,minLat,maxLon,maxLat"),
            },
            required=["server_url", "collection_id"]
        )
    ),

    types.FunctionDeclaration(
        name="get_environmental_data",
        description="Get environmental measurements at a location — temperature, wind, ocean data, climate.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "server_url": types.Schema(type=types.Type.STRING),
                "collection_id": types.Schema(type=types.Type.STRING, description="EDR collection e.g. icoads-sst"),
                "longitude": types.Schema(type=types.Type.STRING, description="Longitude of the location"),
                "latitude": types.Schema(type=types.Type.STRING, description="Latitude of the location"),
                "parameter": types.Schema(type=types.Type.STRING, description="What to measure e.g. SST, AIRT, UWND"),
            },
            required=["server_url", "collection_id", "longitude", "latitude"]
        )
    ),

    types.FunctionDeclaration(
        name="list_processes",
        description="List analysis processes available on a server — things it can compute or analyze.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"server_url": types.Schema(type=types.Type.STRING)},
            required=["server_url"]
        )
    ),

    types.FunctionDeclaration(
        name="run_analysis",
        description="Run a geospatial analysis process on a server.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "server_url": types.Schema(type=types.Type.STRING),
                "process_id": types.Schema(type=types.Type.STRING, description="Process to run"),
                "inputs_json": types.Schema(type=types.Type.STRING, description="Inputs as JSON string"),
            },
            required=["server_url", "process_id", "inputs_json"]
        )
    ),

    types.FunctionDeclaration(
        name="search_metadata",
        description="Search metadata catalogs for datasets about any topic.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "server_url": types.Schema(type=types.Type.STRING),
                "catalog_id": types.Schema(type=types.Type.STRING, description="Catalog collection ID"),
                "topic": types.Schema(type=types.Type.STRING, description="What to search for"),
                "limit": types.Schema(type=types.Type.INTEGER, description="Max results"),
            },
            required=["server_url", "catalog_id", "topic"]
        )
    ),

])

# ─────────────────────────────────────────────────────────────────
# Known Servers Registry
# ─────────────────────────────────────────────────────────────────

KNOWN_SERVERS = {
    "pygeoapi_demo": {
        "url": "https://demo.pygeoapi.io/master",
        "name": "pygeoapi Demo Server",
        "best_for": ["netherlands", "dutch", "windmills", "castles", "lakes", "ocean", "sea temperature", "climate", "metadata", "EDR", "european features", "observations", "airports"],
        "collections_count": 17,
        "has_processes": True,
        "has_records": True,
        "has_edr": True,
        "notable": ["dutch_windmills", "dutch_castles", "lakes", "icoads-sst (ocean temperature)", "dutch-metadata (309 records)"]
    },
    "gnosis_earth": {
        "url": "https://maps.gnosis.earth/ogcapi",
        "name": "Gnosis Maps Server",
        "best_for": ["global", "worldwide", "any country", "elevation", "terrain", "natural earth", "rivers", "cities", "countries", "africa", "asia", "america", "europe", "routing", "point cloud"],
        "collections_count": 749,
        "has_processes": True,
        "has_records": False,
        "has_edr": False,
        "notable": ["NaturalEarth countries/rivers/cities", "ElevationContours process", "749 global collections", "OSMERE routing"]
    },
    "local_munster": {
        "url": "http://localhost:5000",
        "name": "Münster GSoC Demo Server",
        "best_for": ["munster", "münster", "germany", "parks", "cool spot", "urban heat", "city planning", "buffer", "cooling zones"],
        "collections_count": 1,
        "has_processes": True,
        "has_records": False,
        "has_edr": False,
        "notable": ["parks collection", "cool-spot-demo process", "geospatial-buffer process"]
    }
}


# ─────────────────────────────────────────────────────────────────
# Tool Executor
# ─────────────────────────────────────────────────────────────────

async def execute_tool(name: str, args: dict) -> str:
    try:

        if name == "list_known_servers":
            r = "Known OGC API Servers:\n\n"
            for key, s in KNOWN_SERVERS.items():
                r += f"🌍 {s['name']}\n"
                r += f"   URL: {s['url']}\n"
                r += f"   Best for: {', '.join(s['best_for'][:6])}\n"
                r += f"   Collections: {s['collections_count']}\n"
                r += f"   Notable data: {', '.join(s['notable'][:3])}\n\n"
            return r

        server_url = args.get("server_url", "")

        async with OGCClient(server_url) as ogc:

            if name == "discover_server":
                info = await ogc.get_server_info()
                cols = await ogc.get_collections()
                r = f"Server: {info.title}\n"
                r += f"Description: {info.description}\n"
                r += f"Capabilities: {', '.join(info.capabilities)}\n"
                r += f"Total collections: {len(cols)}\n"
                r += "Sample collections:\n"
                for c in cols[:6]:
                    r += f"  [{c.id}] {c.title}\n"
                if len(cols) > 6:
                    r += f"  ... and {len(cols)-6} more\n"
                return r

            elif name == "list_collections":
                cols = await ogc.get_collections()
                r = f"Found {len(cols)} collections on {server_url}:\n\n"
                for c in cols:
                    r += f"  [{c.id}] {c.title}"
                    if c.description:
                        r += f"\n    → {c.description[:80]}"
                    r += "\n"
                return r

            elif name == "find_collection":
                keyword = args.get("keyword", "").lower()
                cols = await ogc.get_collections()
                matches = []
                for c in cols:
                    score = 0
                    title_lower = c.title.lower()
                    id_lower = c.id.lower()
                    desc_lower = (c.description or "").lower()
                    if keyword in id_lower:
                        score += 3
                    if keyword in title_lower:
                        score += 2
                    if keyword in desc_lower:
                        score += 1
                    # partial match
                    for word in keyword.split():
                        if word in id_lower or word in title_lower:
                            score += 1
                    if score > 0:
                        matches.append((score, c))
                matches.sort(key=lambda x: x[0], reverse=True)
                if matches:
                    r = f"Found {len(matches)} collections matching '{keyword}':\n\n"
                    for score, c in matches[:5]:
                        r += f"  [{c.id}] {c.title} (relevance: {score})\n"
                        if c.description:
                            r += f"    {c.description[:80]}\n"
                    r += f"\nBest match: {matches[0][1].id}"
                    return r
                else:
                    # return top collections anyway
                    r = f"No exact match for '{keyword}'. Available collections:\n"
                    for c in cols[:8]:
                        r += f"  [{c.id}] {c.title}\n"
                    return r

            elif name == "get_features":
                data = await ogc.get_features(
                    collection_id=args.get("collection_id"),
                    limit=args.get("limit", 10),
                    bbox=args.get("bbox")
                )
                features = data.get("features", [])
                total = data.get("numberMatched", len(features))
                bbox = args.get("bbox", "")
                r = f"Found {total} features"
                if bbox:
                    r += f" in area [{bbox}]"
                r += f" — showing {len(features)}:\n\n"
                for i, f in enumerate(features, 1):
                    props = f.get("properties", {})
                    name_val = (props.get("name") or props.get("NAME") or
                               props.get("title") or props.get("ADMIN") or
                               f.get("id") or f"Feature {i}")
                    geom = f.get("geometry", {})
                    geom_type = geom.get("type", "")
                    r += f"{i}. {name_val}"
                    if geom_type:
                        r += f" [{geom_type}]"
                    r += "\n"
                    # show key properties
                    shown = 0
                    for k, v in props.items():
                        if k.lower() not in ("name", "title", "admin", "fid", "id", "gid") and v and shown < 3:
                            r += f"   {k}: {v}\n"
                            shown += 1
                return r

            elif name == "get_environmental_data":
                lon = args.get("longitude", "0")
                lat = args.get("latitude", "0")
                coords = f"POINT({lon} {lat})"
                data = await ogc.query_edr_position(
                    collection_id=args.get("collection_id"),
                    coords=coords,
                    parameter_name=args.get("parameter")
                )
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except Exception:
                        return data
                ranges = data.get("ranges", {})
                r = f"Environmental data at lon={lon}, lat={lat}:\n\n"
                if not ranges:
                    return r + "No data returned for this location."
                for param_id, param_data in ranges.items():
                    values = param_data.get("values", [])
                    unit = param_data.get("unit", {})
                    unit_label = unit.get("label", {})
                    unit_str = unit_label.get("en", "") if isinstance(unit_label, dict) else str(unit_label)
                    numeric = [v for v in values if v is not None]
                    if numeric:
                        avg = sum(numeric) / len(numeric)
                        r += f"  {param_id}: avg={avg:.2f} {unit_str}\n"
                        r += f"    min={min(numeric):.2f}, max={max(numeric):.2f}\n"
                        r += f"    ({len(numeric)} data points)\n"
                return r

            elif name == "list_processes":
                procs = await ogc.get_processes()
                r = f"Found {len(procs)} processes on {server_url}:\n\n"
                for p in procs:
                    r += f"  [{p.id}]\n"
                    r += f"  Title: {p.title}\n"
                    if p.description:
                        r += f"  Description: {p.description[:100]}\n"
                    r += "\n"
                return r

            elif name == "run_analysis":
                inputs_json = args.get("inputs_json", "{}")
                try:
                    inputs = json.loads(inputs_json)
                except json.JSONDecodeError:
                    inputs = {}
                process_id = args.get("process_id")
                output = await ogc.execute_process(
                    process_id=process_id,
                    inputs=inputs,
                    async_execute=False
                )
                result_str = json.dumps(output, indent=2, ensure_ascii=False)
                return f"Analysis '{process_id}' complete:\n\n{result_str[:3000]}"

            elif name == "search_metadata":
                results = await ogc.search_records(
                    collection_id=args.get("catalog_id"),
                    q=args.get("topic"),
                    limit=args.get("limit", 8)
                )
                features = results.get("features", [])
                total = results.get("numberMatched", len(features))
                topic = args.get("topic", "")
                r = f"Found {total} datasets about '{topic}' (showing {len(features)}):\n\n"
                for i, f in enumerate(features, 1):
                    props = f.get("properties", {})
                    title = props.get("title", "Untitled")
                    desc = props.get("description", "")
                    rec_type = props.get("type", "")
                    r += f"{i}. {title}"
                    if rec_type:
                        r += f" [{rec_type}]"
                    r += "\n"
                    if desc:
                        r += f"   {desc[:120]}\n"
                return r

            else:
                return f"Unknown tool: {name}"

    except Exception as e:
        return f"Tool error ({name}): {type(e).__name__}: {str(e)}"


# ─────────────────────────────────────────────────────────────────
# Conversation Runner
# ─────────────────────────────────────────────────────────────────

def ask(question: str, verbose: bool = True) -> str:
    """Ask any geospatial question. Returns Gemini's answer."""
    loop = asyncio.get_event_loop()

    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=question)])
    ]

    for turn in range(8):
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=AUTONOMOUS_SYSTEM_PROMPT,
                tools=[TOOLS],
                temperature=0.1,
            )
        )

        function_calls = response.function_calls
        if not function_calls:
            return response.text or "No response generated."

        contents.append(response.candidates[0].content)

        tool_parts = []
        for fc in function_calls:
            tool_args = dict(fc.args) if fc.args else {}

            if verbose:
                key_arg = (tool_args.get("keyword") or
                           tool_args.get("collection_id") or
                           tool_args.get("topic") or
                           tool_args.get("process_id") or
                           tool_args.get("server_url", "")[:35])
                print(f"    🔧 {fc.name}({key_arg})")

            result = loop.run_until_complete(execute_tool(fc.name, tool_args))

            tool_parts.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result[:4000]}
                )
            )

        contents.append(types.Content(role="tool", parts=tool_parts))

    return "Reached max reasoning steps."


# ─────────────────────────────────────────────────────────────────
# Showcase Scenarios — The Real Demo
# ─────────────────────────────────────────────────────────────────

SHOWCASE = [
    {
        "title": "🌊 Ocean Conditions",
        "question": "What are the ocean conditions in the middle of the Atlantic Ocean at longitude -30, latitude 45? Is it warm or cold water?"
    },
    {
        "title": "🏰 Cultural Heritage",
        "question": "Find historic windmills and castles near Utrecht in the Netherlands. What is the cultural heritage like in that region?"
    },
    {
        "title": "🌍 Global Features",
        "question": "Show me major rivers in Africa. Which ones are available in the geospatial data?"
    },
    {
        "title": "🏙️ Urban Cool Spot Analysis",
        "question": "I am an urban planner in Münster. Which of the city parks provides the best cooling effect for residents? Run the analysis."
    },
    {
        "title": "📚 Historical Research",
        "question": "I am researching Dutch flood history. What historical datasets about water management are available?"
    },
    {
        "title": "🗺️ Terrain Analysis",
        "question": "I want to understand what terrain analysis processes are available for global elevation data. What can the Gnosis server do?"
    },
]


def run_showcase():
    print("=" * 70)
    print("  AUTONOMOUS GEOSPATIAL ASSISTANT")
    print("  GSoC 2026: MCP for OGC APIs @ 52°North")
    print("=" * 70)
    print()
    print("  ✨ No server URLs. No technical parameters.")
    print("  ✨ Just ask. The system figures out everything.")
    print()
    print(f"  Model:   {GEMINI_MODEL}")
    print(f"  Servers: 3 real OGC API servers")
    print(f"  Tools:   9 autonomous discovery tools")
    print()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    passed = 0
    for scenario in SHOWCASE:
        print("─" * 70)
        print(f"  {scenario['title']}")
        print("─" * 70)
        print(f"\n  User: \"{scenario['question']}\"")
        print()
        print("  [System autonomously selecting server and tools...]")
        print()

        try:
            answer = ask(scenario["question"])
            print(f"  Assistant: {answer}")
            passed += 1
        except Exception as e:
            print(f"  ERROR: {e}")

        print()

    loop.close()

    print("=" * 70)
    print(f"  {passed}/{len(SHOWCASE)} scenarios completed")
    print("  ✅ Fully autonomous — zero server URLs from user")
    print("  ✅ Multiple real OGC servers used automatically")
    print("  ✅ Natural language in → plain language out")
    print("=" * 70)


def run_chat():
    print("=" * 70)
    print("  AUTONOMOUS GEOSPATIAL ASSISTANT — Chat Mode")
    print("=" * 70)
    print()
    print("  Ask ANYTHING about the world — locations, climate,")
    print("  terrain, historical data, urban analysis.")
    print()
    print("  No server URLs needed. No GIS knowledge needed.")
    print("  Just ask in plain English.")
    print()
    print("  Try:")
    print("  → What are the lakes in Canada?")
    print("  → What is the sea temperature near Iceland?")
    print("  → Show me countries in Southeast Asia")
    print("  → Analyze cooling zones for Münster parks")
    print("  → Find historical water management data in Netherlands")
    print("  → What terrain analysis can I do with global data?")
    print()
    print("  Type 'quit' to exit.")
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
            answer = ask(user_input)
            print(f"Assistant: {answer}")
        except Exception as e:
            print(f"Error: {e}")
        print()

    loop.close()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "chat"
    if mode == "demo":
        run_showcase()
    else:
        run_chat()
