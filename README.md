# OGC MCP Server

An MCP (Model Context Protocol) server that bridges natural language
and OGC API-compliant geospatial servers. Built as part of GSoC 2026
@ 52°North Spatial Information Research GmbH.

## What It Does

Allows any LLM (Claude, Gemini, GPT) to interact with geospatial data
and spatial analysis processes on any OGC-compliant server through
natural language — no GIS expertise required.

**Example:** "Find all lakes in Europe" → MCP server → OGC API Features
→ GeoJSON returned to LLM → plain language answer to user.

**Example:** "Run a cool spot analysis on my park data" → MCP server →
OGC API Processes → job submitted → results returned to LLM.

## Architecture
```
LLM (Gemini / Claude / GPT)
        ↕ MCP Protocol (JSON-RPC 2.0 over stdio)
OGC MCP Server (this repo)
   ├── server.py      → FastMCP server, tool/resource/prompt registration
   ├── ogc_client.py  → Pure HTTP client for any OGC API server
   └── mapper.py      → Translates OGC objects into MCP objects
        ↕ OGC API REST (HTTP/JSON)
OGC Backend (pygeoapi / GeoServer / any conforming server)
```

## MCP Tools Exposed (9 Total)

| Tool | Description |
|------|-------------|
| `discover_ogc_server` | Discover capabilities of any OGC API server |
| `get_collections` | List all available geospatial datasets |
| `get_collection_detail` | Get metadata and extent for a specific collection |
| `get_features` | Fetch GeoJSON features with bbox/temporal/CQL2 filtering |
| `discover_processes` | List all available spatial analysis processes |
| `get_process_detail` | Get full input/output schema for a process |
| `execute_process` | Execute any process synchronously or asynchronously |
| `get_job_status` | Monitor an async processing job |
| `get_job_results` | Retrieve completed job output |

## MCP Resources (3 Total)

| Resource URI | Description |
|-------------|-------------|
| `ogc://collections/list` | All available datasets on the default server |
| `ogc://processes/list` | All available processes on the default server |
| `ogc://server/info` | Server title, description, and capabilities |

## MCP Prompts — Generic Workflow Templates (3 Total)

| Prompt | Description |
|--------|-------------|
| `spatial_analysis_workflow` | Any spatial analysis end to end (buffer, cool spot, zonal stats, etc.) |
| `data_discovery_workflow` | Find and fetch relevant geodata by topic and location |
| `server_exploration_workflow` | Fully explore an unknown OGC server |

> Prompts are intentionally generic — not hardcoded to cool spot analysis.
> Any OGC-supported operation works through natural language.

## Supported OGC APIs

| API | Status |
|-----|--------|
| OGC API — Features | ✅ Complete |
| OGC API — Processes | ✅ Complete |
| OGC API — Records | 🔄 In progress |
| OGC API — EDR | 🔄 In progress |

## Quick Start
```bash
# Clone and install
git clone https://github.com/hanzila1/ogc-mcp-server
cd ogc-mcp-server
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Launch MCP Inspector (browser UI)
mcp dev main.py

# Run full client test
python examples/test_mcp_client.py
```

## Project Structure
```
ogc-mcp-server/
├── src/
│   └── ogc_mcp/
│       ├── __init__.py
│       ├── server.py       ← FastMCP server (Tools, Resources, Prompts)
│       ├── ogc_client.py   ← Pure OGC HTTP client (zero MCP dependencies)
│       └── mapper.py       ← OGC → MCP translation layer
├── tests/
│   └── test_ogc_client.py  ← 10 integration tests (all passing)
├── examples/
│   ├── explore_ogc.py          ← OGC API exploration script
│   ├── ogc_exploration.http    ← REST Client requests
│   └── test_mcp_client.py      ← 12 MCP client tests (all passing)
├── schemas/                    ← JSON schema mappings (Stage 4)
├── docker/                     ← pygeoapi Docker config (Stage 3)
├── main.py                     ← Entry point
├── requirements.txt
└── README.md
```

## Verification Results

Tested against live `demo.pygeoapi.io` via MCP Inspector and client script:
```
✓ 9 tools discovered and callable
✓ 3 resources readable
✓ 3 workflow prompts working
✓ 17 collections dynamically discovered
✓ Spatial bbox filtering verified (25 global lakes → 3 European lakes)
✓ OGC process executed end to end
✓ Async job lifecycle working
✓ 12/12 MCP client tests passing
✓ 10/10 unit tests passing
```

## Compatibility

Works against any OGC API-compliant server without code changes:
- [pygeoapi](https://pygeoapi.io/) — Python OGC API server
- [GeoServer](https://geoserver.org/) — Java OGC API server
- [ldproxy](https://github.com/interactive-instruments/ldproxy) — OGC API proxy
- Any other OGC-conformant implementation

## GSoC 2026

Developed for the 52°North GSoC 2026 project:
**"MCP for OGC APIs — Developing Multi Context Protocols for the suite of OGC APIs"**

Mentors: Benjamin Pross, Benedikt Gräler
Organization: [52°North Spatial Information Research GmbH](https://52north.org/)

## License

Apache Software License, Version 2.0