# OGC API → MCP Mapping — Quick Reference

## Complete Mapping Summary

### Legend
- 🔧 **Tool** — Active operation the LLM invokes
- 📄 **Resource** — Read-only context the LLM consults  
- 💬 **Prompt** — Reusable workflow template

---

### OGC API — Common (shared by all API types)

| # | OGC Concept | Endpoint | MCP | MCP Name |
|---|-----------|----------|-----|----------|
| C1 | Landing Page | `GET /` | 🔧 Tool | `discover_ogc_server` |
| C2 | Conformance | `GET /conformance` | 🔧 Tool | `get_conformance` |
| C3 | Collections List | `GET /collections` | 🔧 Tool | `get_collections` |
| C4 | Collection Metadata | `GET /collections/{id}` | 📄 Resource | `ogc://{server}/collections/{id}` |

### OGC API — Features

| # | OGC Concept | Endpoint | MCP | MCP Name |
|---|-----------|----------|-----|----------|
| F1 | Feature Collection | `GET /collections/{id}` | 📄 Resource | `ogc://{server}/collections/{id}` |
| F2 | Get Features | `GET /collections/{id}/items` | 🔧 Tool | `get_features` |
| F3 | Get Feature by ID | `GET /collections/{id}/items/{fid}` | 🔧 Tool | `get_feature_by_id` |
| F4 | Spatial Query | `GET .../items?bbox=...` | 🔧 Tool | `spatial_query_features` |
| F5 | Queryables | `GET /collections/{id}/queryables` | 📄 Resource | `ogc://{server}/collections/{id}/queryables` |
| F6 | Analysis Workflow | *(composite)* | 💬 Prompt | `spatial_analysis_workflow` |

### OGC API — Records

| # | OGC Concept | Endpoint | MCP | MCP Name |
|---|-----------|----------|-----|----------|
| R1 | Catalog Metadata | `GET /collections/{catId}` | 📄 Resource | `ogc://{server}/catalogs/{id}` |
| R2 | Search Records | `GET /collections/{catId}/items?q=...` | 🔧 Tool | `search_catalog` |
| R3 | Get Record by ID | `GET .../items/{recId}` | 🔧 Tool | `get_catalog_record` |
| R4 | Discovery Workflow | *(composite)* | 💬 Prompt | `data_discovery_workflow` |

### OGC API — Environmental Data Retrieval (EDR)

| # | OGC Concept | Endpoint | MCP | MCP Name |
|---|-----------|----------|-----|----------|
| E1 | EDR Collection | `GET /collections/{id}` | 📄 Resource | `ogc://{server}/edr/{id}` |
| E2 | Position Query | `GET .../position?coords=POINT(...)` | 🔧 Tool | `edr_position_query` |
| E3 | Area Query | `GET .../area?coords=POLYGON(...)` | 🔧 Tool | `edr_area_query` |
| E4 | Trajectory Query | `GET .../trajectory?coords=LINESTRING(...)` | 🔧 Tool | `edr_trajectory_query` |
| E5 | Cube Query | `GET .../cube?bbox=...` | 🔧 Tool | `edr_cube_query` |
| E6 | Radius Query | `GET .../radius?coords=...&within=...` | 🔧 Tool | `edr_radius_query` |
| E7 | Locations Query | `GET .../locations` | 🔧 Tool | `edr_list_locations` |
| E8 | Analysis Workflow | *(composite)* | 💬 Prompt | `environmental_analysis_workflow` |

### OGC API — Processes

| # | OGC Concept | Endpoint | MCP | MCP Name |
|---|-----------|----------|-----|----------|
| P1 | Process (dynamic) | `GET /processes/{id}` | 🔧 Tool | `execute_{process_id}` *(auto-generated)* |
| P2 | Process List | `GET /processes` | 🔧 Tool | `discover_processes` |
| P3 | Execute Process | `POST /processes/{id}/execution` | 🔧 Tool | `execute_process` |
| P4 | Job Status | `GET /jobs/{jobId}` | 🔧 Tool | `get_job_status` |
| P5 | Job Results | `GET /jobs/{jobId}/results` | 🔧 Tool | `get_job_results` |
| P6 | Dismiss Job | `DELETE /jobs/{jobId}` | 🔧 Tool | `dismiss_job` |
| P7 | Execution Workflow | *(composite)* | 💬 Prompt | `process_execution_workflow` |

---

## Totals

| MCP Primitive | Count | Purpose |
|--------------|-------|---------|
| 🔧 **Tools** | 20 | Active operations: discovery, querying, execution, monitoring |
| 📄 **Resources** | 6 | Contextual metadata: collections, queryables, catalogs, EDR parameters |
| 💬 **Prompts** | 4 | Multi-step workflows: spatial analysis, data discovery, EDR analysis, process execution |
| **Total** | **30** | Complete OGC API coverage across 4 API types + Common |

---

## The Three-Layer Architecture

```
┌─────────────────────────────────────────────────┐
│                   LLM / Agent                    │
│    "Conduct a cool spot analysis for parks"      │
└───────────────────────┬─────────────────────────┘
                        │  MCP Protocol (JSON-RPC 2.0)
                        │
┌───────────────────────▼─────────────────────────┐
│              MCP Server (ogc-mcp-server)          │
│                                                   │
│  📄 Resources  │  🔧 Tools   │  💬 Prompts       │
│  (collection   │  (queries,  │  (workflow         │
│   metadata,    │   execution,│   templates)       │
│   queryables)  │   jobs)     │                    │
│                                                   │
│  mapper.py — applies mapping rules from schema    │
└───────────────────────┬─────────────────────────┘
                        │  HTTP/HTTPS
                        │
┌───────────────────────▼─────────────────────────┐
│           OGC API Backend(s)                      │
│  pygeoapi │ GeoServer │ MapServer │ any OGC API   │
│                                                   │
│  Features │ Records │ EDR │ Processes │ Common    │
└─────────────────────────────────────────────────┘
```

---

## Cool Spot Analysis — End-to-End MCP Flow

The project description's scenario mapped to MCP primitives:

```
1. Urban planner asks: "Conduct a cool spot analysis 
   based on the new parks I designed for the city"
                    │
                    ▼
2. 💬 Prompt: process_execution_workflow
   → LLM follows the step-by-step template
                    │
                    ▼
3. 📄 Resource: Collection metadata for "parks"
   → LLM reads extent, properties, item type
                    │
                    ▼
4. 🔧 Tool: get_features (collection="parks")
   → Retrieves park boundary GeoJSON
                    │
                    ▼
5. 🔧 Tool: discover_processes
   → Finds "cool-spot-analysis" process
                    │
                    ▼
6. 📄 Resource: Process description  
   → LLM reads required inputs, understands schema
                    │
                    ▼
7. 🔧 Tool: execute_cool_spot_analysis
   → Submits park boundaries + parameters
                    │
                    ▼
8. 🔧 Tool: get_job_status (if async)
   → Monitors execution progress
                    │
                    ▼
9. 🔧 Tool: get_job_results
   → Retrieves cooling zones, temperature reductions
                    │
                    ▼
10. LLM presents results to planner:
    "Aasee Park: 4.0°C reduction, High intensity"
```
