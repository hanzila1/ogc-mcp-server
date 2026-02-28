# OGC MCP Server
### GSoC 2026 · 52°North Spatial Information Research GmbH

> **Bridging natural language and geospatial data through the Model Context Protocol and OGC APIs.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Tests: 221 passing](https://img.shields.io/badge/tests-221%20passing-brightgreen.svg)](#testing)
[![GSoC 2026](https://img.shields.io/badge/GSoC-2026-orange.svg)](https://summerofcode.withgoogle.com/)
[![52North](https://img.shields.io/badge/org-52°North-green.svg)](https://52north.org/)

---

## The Vision

A non-expert urban planner types:

> *"Which of my city parks provides the best cooling effect for residents?"*

The system **autonomously**:
- Selects the right OGC server
- Discovers the cool spot analysis process
- Executes the analysis with park data
- Returns a plain-language answer

No GIS expertise. No server URLs. No technical parameters. Just ask.

This project builds a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that bridges Large Language Models with the full suite of [OGC APIs](https://ogcapi.ogc.org/), making geospatial data and analysis accessible to everyone through natural language.

---

## Live Demo Output

```
User: "Which Münster park provides the best cooling effect for residents?"

  System thinking...
  🔧 list_processes(localhost:5000)
  🔧 get_features(parks)
  🔧 run_analysis(cool-spot-demo)

  Assistant: Schlosspark has the highest tree coverage at 80%, making it the most
  efficient cooling park per unit area. Central Park, being 341 ha, provides the
  largest overall cooling contribution to the city. Aasee Park with its water body
  adds additional cooling through evaporation.
```

```
User: "Show me major rivers in Africa"

  System thinking...
  🔧 find_collection(rivers)        → gnosis.earth (749 global collections)
  🔧 get_features(NaturalEarth rivers, bbox=-18,-35,52,38)

  Assistant: Found rivers including the Ogooué, Pongola, Cuito, Gwayi across
  central and southern Africa. The dataset uses scalerank to indicate river
  prominence — I can refine by specific country or region if needed.
```

```
User: "What are ocean conditions near Iceland? Is it warm or cold?"

  System thinking...
  🔧 get_environmental_data(icoads-sst, lon=-20, lat=65)

  Assistant: Sea surface temperature near Iceland averages 4.2°C — this is
  cold North Atlantic water, heavily influenced by the East Greenland Current.
```

**Three completely different OGC servers. Three different API types. Zero server URLs from the user.**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER (Natural Language)                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              LLM (Gemini 2.5 Flash)                             │
│   Understands intent → selects tools → interprets results       │
└──────────────────────────────┬──────────────────────────────────┘
                               │  Function Calling
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              MCP Server (FastMCP)                               │
│                                                                 │
│  13 Fixed Tools          Dynamic Tools (auto-generated)         │
│  ─────────────           ────────────────────────────          │
│  discover_server         execute_{process_id}                   │
│  list_collections        (one per OGC process discovered)       │
│  get_features                                                   │
│  search_catalog          3 Resources                            │
│  query_edr_position      ─────────                             │
│  execute_process         ogc://collections/list                 │
│  get_job_status          ogc://processes/list                   │
│  get_job_results         ogc://server/info                      │
│  ... and more                                                   │
│                          3 Workflow Prompts                     │
└──────────────────────────────┬──────────────────────────────────┘
                               │  HTTP (OGC API Standard)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              OGCClient (server-agnostic HTTP layer)             │
│                                                                 │
│  Any OGC-compliant server works — zero code changes needed      │
└───────────┬──────────────────┬──────────────────┬──────────────┘
            │                  │                  │
            ▼                  ▼                  ▼
   demo.pygeoapi.io    maps.gnosis.earth   localhost:5000
   (Netherlands data,  (749 global         (Münster parks,
    ocean/climate,      collections,        cool spot demo,
    Dutch metadata)     elevation,          custom processes)
                        NaturalEarth)
```

### Core Modules

| File | Purpose |
|------|---------|
| `src/ogc_mcp/ogc_client.py` | Pure async HTTP client for all OGC API types |
| `src/ogc_mcp/mapper.py` | Translates OGC objects → MCP protocol objects |
| `src/ogc_mcp/server.py` | FastMCP server — tools, resources, prompts |
| `main.py` | Entry point for MCP server |

### Key Innovation — Dynamic Tool Generation

Every OGC Process automatically becomes an MCP Tool:

```python
# Server connects to any OGC endpoint
# Calls /processes to discover available processes
# Automatically generates MCP Tools from process descriptions

# Connected to demo.pygeoapi.io:
#   13 fixed tools + 6 dynamic = 19 tools total

# Connected to maps.gnosis.earth:
#   13 fixed tools + 11 dynamic = 24 tools total

# Connected to localhost:5000:
#   13 fixed tools + 2 dynamic = 15 tools total
```

When a server adds a new process, your MCP client picks it up automatically. Zero maintenance.

---

## OGC API Coverage

| OGC API | Status | Tools |
|---------|--------|-------|
| Features | ✅ Complete | `get_collections`, `get_features`, `get_collection_detail` |
| Processes | ✅ Complete | `discover_processes`, `execute_process`, `get_job_status`, `get_job_results` + dynamic |
| Records | ✅ Complete | `search_catalog`, `get_catalog_record` |
| EDR | ✅ Complete | `query_edr_position`, `query_edr_area` |
| Common | ✅ Complete | `discover_ogc_server` |

---

## Project Structure

```
ogc-mcp-server/
│
├── src/ogc_mcp/              # Core library
│   ├── __init__.py
│   ├── ogc_client.py         # Async HTTP client for all OGC API types
│   ├── mapper.py             # OGC → MCP translation layer
│   └── server.py             # FastMCP server implementation
│
├── examples/                 # Demo scripts
│   ├── autonomous_demo.py    # ★ Autonomous geospatial assistant (main demo)
│   ├── gemini_mcp_demo.py    # Gemini LLM integration with 5 scenarios
│   ├── test_stage5_e2e.py    # End-to-end integration tests
│   ├── test_stage5_part2.py  # Records + EDR tests
│   ├── test_stage5_part3.py  # Dynamic tool generation tests
│   ├── test_multi_server.py  # Multi-server compatibility tests
│   ├── test_mcp_client.py    # MCP protocol tests
│   └── test_stage3.py        # Docker backend tests
│
├── tests/                    # Unit tests
│   ├── test_ogc_client.py    # OGC HTTP client tests (10 tests)
│   └── test_schema_mapping.py # JSON schema validation (30 tests)
│
├── schemas/                  # Formal MCP-OGC mapping specification
│   ├── ogc-mcp-mapping.schema.json      # Meta-schema (29 mapping rules)
│   ├── ogc-mcp-mapping-instance.json    # Concrete mapping instance
│   ├── MAPPING_RATIONALE.md             # Design decisions explained
│   └── mapping-summary.md               # Quick reference
│
├── docker/                   # OGC API Processes backend
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── pygeoapi/
│       ├── pygeoapi-config.yml
│       ├── data/
│       │   └── parks.geojson            # Münster parks dataset
│       └── processes/
│           ├── cool_spot_analysis.py    # Urban heat island analysis
│           └── geospatial_buffer.py     # Spatial buffer process
│
├── main.py                   # MCP server entry point
├── requirements.txt
├── .env.example              # Environment variable template
└── .gitignore
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Docker (for the local OGC backend)
- Gemini API key ([get one free](https://aistudio.google.com/apikey))

### 1. Clone and Install

```bash
git clone https://github.com/hanzila1/ogc-mcp-server.git
cd ogc-mcp-server

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
```env
OGC_SERVER_URL=https://demo.pygeoapi.io/master
GEMINI_API_KEY=your_gemini_api_key_here
```

Your API key is never committed to git — `.env` is in `.gitignore`.

### 3. Start the Local OGC Backend (Docker)

```bash
# Build the Münster parks + cool spot analysis backend
docker build -t ogc-mcp-pygeoapi ./docker

# Run it
docker run -p 5000:80 --name ogc-backend ogc-mcp-pygeoapi

# Verify it works
curl http://localhost:5000/processes
```

To restart:
```bash
docker stop ogc-backend
docker rm ogc-backend
docker run -p 5000:80 --name ogc-backend ogc-mcp-pygeoapi
```

### 4. Run the Autonomous Demo

```bash
# Interactive chat — just ask anything
python examples/autonomous_demo.py

# Automated showcase — 6 scenarios across 3 servers
python examples/autonomous_demo.py demo
```

### 5. Run the Gemini LLM Demo (5 scenarios)

```bash
python examples/gemini_mcp_demo.py
```

### 6. Start the MCP Server

```bash
python main.py
```

The server runs via stdio transport, ready to connect to any MCP-compatible LLM client (Claude Desktop, etc.).

---

## Demo Scenarios

### Autonomous Assistant (no server URLs needed)

```bash
python examples/autonomous_demo.py
```

Try these prompts:

```
What are the ocean conditions near Iceland?
Show me major rivers in Africa
Find historic windmills near Utrecht in the Netherlands
Which Münster park is best for urban cooling?
What historical Dutch water management datasets exist?
What terrain analysis can I do with global elevation data?
What are lakes in Canada?
Find cultural heritage sites in the Netherlands
```

### Gemini LLM Integration

```bash
python examples/gemini_mcp_demo.py
```

Runs 5 automated scenarios:
1. Server discovery — what data is available?
2. Feature query — lakes in Europe with bbox filter
3. Cool spot analysis — the exact 52°North urban planner scenario
4. Catalog search — Dutch metadata records
5. EDR query — Mediterranean sea surface temperature

### Multi-Server Compatibility Test

```bash
python examples/test_multi_server.py
```

Proves the same client works against three independent servers:
- `demo.pygeoapi.io` — 17 collections, 6 processes
- `localhost:5000` — custom Münster backend
- `maps.gnosis.earth` — 749 collections, 11 processes

---

## Testing

221 tests across 7 test files, all passing.

```bash
# Run all tests
pytest tests/ examples/ -v

# Individual test suites
pytest tests/test_ogc_client.py -v          # OGC HTTP client (10 tests)
pytest tests/test_schema_mapping.py -v      # JSON schema spec (30 tests)
pytest examples/test_mcp_client.py -v       # MCP protocol (12 tests)
pytest examples/test_stage5_e2e.py -v       # End-to-end (35 tests)
pytest examples/test_stage5_part2.py -v     # Records + EDR (35 tests)
pytest examples/test_stage5_part3.py -v     # Dynamic tools (92 tests)
```

### Test Results Summary

```
tests/test_ogc_client.py          10 tests  ✅
tests/test_schema_mapping.py      30 tests  ✅
examples/test_mcp_client.py       12 tests  ✅
examples/test_stage3.py            7 tests  ✅
examples/test_stage5_e2e.py       35 tests  ✅
examples/test_stage5_part2.py     35 tests  ✅
examples/test_stage5_part3.py     92 tests  ✅

Total: 221 tests — all passing
```

---

## The MCP-OGC Mapping Specification

A formal JSON schema specification defining 29 concrete rules for translating OGC API concepts into MCP protocol objects. Located in `schemas/`.

### Coverage

```
OGC API Common    → MCP Server metadata, capabilities
OGC API Features  → MCP Tools (get_features, get_collections...)
OGC API Processes → MCP Tools (dynamic: execute_{process_id})
OGC API Records   → MCP Tools (search_catalog, get_catalog_record)
OGC API EDR       → MCP Tools (query_edr_position, query_edr_area)
```

### Key Design Decisions

**Dynamic Process Mapping** — Each OGC Process becomes an MCP Tool at runtime. The inputSchema is derived directly from the OGC process description. When new processes are added to a server, they appear as MCP Tools automatically with no code changes.

**Server-Agnostic Architecture** — The server URL is always a parameter, never hardcoded. The same MCP client works against any OGC-compliant server worldwide.

**Modular Design** — Each OGC API type maps independently. Adding support for a new OGC API (e.g., Coverages, Tiles) requires only new mapper functions, not architectural changes.

Read `schemas/MAPPING_RATIONALE.md` for full design rationale.

---

## Local OGC API Processes Backend

The Docker backend demonstrates a complete OGC API Processes deployment with two custom geospatial processes.

### Cool Spot Analysis

The key scenario from the 52°North project description — urban heat island analysis for park planning.

**Endpoint:** `POST /processes/cool-spot-demo/execution`

**Input:**
```json
{
  "inputs": {
    "park_geometries": {
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "properties": {
            "name": "Aasee Park",
            "area_ha": 52.3,
            "tree_coverage": 0.45,
            "has_water": true
          },
          "geometry": {
            "type": "Polygon",
            "coordinates": [[[7.607,51.949],[7.617,51.949],[7.617,51.957],[7.607,51.957],[7.607,51.949]]]
          }
        }
      ]
    },
    "buffer_km": 0.5,
    "city_name": "Münster"
  }
}
```

**Output:**
```json
{
  "city": "Münster",
  "analysis_results": [
    {
      "park_name": "Aasee Park",
      "cooling_intensity": "High",
      "estimated_temp_reduction_celsius": 4.0,
      "cooling_radius_km": 0.79
    }
  ]
}
```

### Geospatial Buffer

**Endpoint:** `POST /processes/geospatial-buffer/execution`

Creates a buffer zone around any point or geometry — useful for impact assessment, planning zones, and proximity analysis.

### Parks Dataset

```
Central Park   — 341.1 ha, 65% tree coverage
Aasee Park     — 52.3 ha,  45% tree coverage, water body
Schlosspark    — 18.7 ha,  80% tree coverage
```

---

## Real-World Servers Tested

| Server | Type | Collections | Processes | Notes |
|--------|------|-------------|-----------|-------|
| [demo.pygeoapi.io](https://demo.pygeoapi.io/master) | pygeoapi | 17 | 6 | Netherlands data, NOAA ocean EDR, Dutch metadata |
| [maps.gnosis.earth](https://maps.gnosis.earth/ogcapi) | Independent | 749 | 11 | NaturalEarth global data, elevation analysis |
| localhost:5000 | pygeoapi (Docker) | 1 | 2 | Custom Münster parks + cool spot analysis |

The system was tested against all three simultaneously with zero code changes — proving true server-agnostic interoperability.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes (for LLM demos) | Google Gemini API key |
| `OGC_SERVER_URL` | No | Default OGC server (defaults to demo.pygeoapi.io) |

---

## Requirements

```
fastmcp>=0.1.0
httpx>=0.24.0
python-dotenv>=1.0.0
google-genai>=1.0.0
jsonschema>=4.0.0
pytest>=7.0.0
pytest-asyncio>=0.21.0
```

Install:
```bash
pip install -r requirements.txt
```

---

## GSoC 2026 Project Deliverables

This project was developed as part of Google Summer of Code 2026 with [52°North Spatial Information Research GmbH](https://52north.org/).

### Deliverable 1 — Formal MCP-OGC Mapping Specification
- 29 mapping rules in machine-readable JSON schema
- Covers OGC API Features, Processes, Records, EDR, and Common
- Meta-schema for validation
- Design rationale documentation

### Deliverable 2 — Reference MCP Server Implementation
- FastMCP server with 13 fixed tools + dynamic tools per server
- Async OGC HTTP client supporting all 4 API types
- OGC → MCP translation layer
- 221 tests across full stack

### Deliverable 3 — OGC API Processes Backend
- Docker deployment of pygeoapi
- Custom cool spot analysis process (urban heat island scenario)
- Custom geospatial buffer process
- Full OGC Processes lifecycle: /processes, /jobs, /results

### Deliverable 4 — LLM Integration Showcase
- Gemini 2.5 Flash integration with function calling
- Autonomous geospatial assistant (no server URLs from user)
- 6 real-world scenarios across 3 independent OGC servers
- Natural language in → plain language out

### Mentors
- Benjamin Pross · [b.pross@52north.org](mailto:b.pross@52north.org)
- Benedikt Gräler · [b.graeler@52north.org](mailto:b.graeler@52north.org)

---

## License

Apache Software License, Version 2.0 — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [52°North Spatial Information Research GmbH](https://52north.org/) for mentorship and the project idea
- [Open Geospatial Consortium](https://www.ogc.org/) for the OGC API standards
- [pygeoapi](https://pygeoapi.io/) for the OGC API server implementation
- [FastMCP](https://github.com/jlowin/fastmcp) for the MCP server framework
- [Google](https://ai.google.dev/) for Gemini API access
- Cool spot analysis concept from [52°North blog post](https://blog.52north.org/2022/12/16/cool-spots-in-munster/)

---

*Built with Python · FastMCP · pygeoapi · Docker · Gemini 2.5 Flash*
