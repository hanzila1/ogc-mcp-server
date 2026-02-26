# OGC API → MCP Mapping Specification — Design Rationale

## GSoC 2026 — 52°North — "MCP for OGC APIs"

**Author:** Hanzila Bin Younus  
**Mentors:** Benjamin Pross, Benedikt Gräler  
**Version:** 1.0.0  
**Date:** February 2026

---

## 1. Purpose

This document explains the design decisions behind the formal JSON schema mapping specification that translates OGC API concepts into MCP (Model Context Protocol) concepts. The specification is the intellectual core of the GSoC project — it defines how geospatial standards become naturally accessible to Large Language Models.

## 2. The Core Design Principle

**Every OGC API concept maps to exactly one of three MCP primitives based on its behavioral nature:**

| Behavior | MCP Primitive | OGC Examples |
|----------|--------------|-------------|
| **Read-only context** — stable metadata the LLM reads to inform decisions | **Resource** | Collection metadata, queryables, catalog entries, EDR parameter descriptions |
| **Active operation** — parameterized action the LLM executes | **Tool** | Feature queries, process execution, job monitoring, catalog search, EDR queries |
| **Reusable workflow** — multi-step template encoding domain expertise | **Prompt** | Spatial analysis workflow, data discovery workflow, process execution workflow |

This three-way classification is not arbitrary. It directly follows the MCP specification's design intent:

- **Resources** are "application-driven" — the client or user selects them to provide context
- **Tools** are "model-controlled" — the LLM discovers and invokes them autonomously
- **Prompts** are "user-triggered" — explicit workflow templates the user or application invokes

## 3. Why This Classification Matters

Consider the urban planner scenario from the project description. When the planner says *"Conduct a cool spot analysis based on the new parks I have designed for the city"*, the LLM needs all three primitives working together:

1. **Resources** provide context: the LLM reads the collection metadata for the parks dataset to understand what fields exist (park name, geometry, area). It reads the process descriptions to know what cool-spot-analysis expects as input.

2. **Tools** perform actions: the LLM calls `get_features` to retrieve the park boundaries, calls `execute_process` with the cool spot analysis parameters, calls `get_job_status` to monitor execution, and calls `get_job_results` to retrieve the output.

3. **Prompts** encode expertise: the `process_execution_workflow` prompt provides the step-by-step structure that guides the LLM through the entire interaction, ensuring it discovers the right process, validates inputs, handles async execution, and presents results meaningfully.

## 4. Mapping Decisions by OGC API Type

### 4.1 OGC API — Common

| OGC Concept | → MCP | Rationale |
|------------|-------|-----------|
| Landing page (`/`) | Tool | Active discovery — the LLM must make a request to learn server capabilities. Dynamic, not static. |
| Conformance (`/conformance`) | Tool | Active capability check — the LLM queries what the server implements before attempting operations. |
| Collections list (`/collections`) | Tool | Active listing — collections may change as data is added/removed. |
| Collection metadata (`/collections/{id}`) | Resource | Stable context — a collection's title, description, extent, and schema rarely change. Canonical URI. |

### 4.2 OGC API — Features

| OGC Concept | → MCP | Rationale |
|------------|-------|-----------|
| Collection metadata | Resource | The LLM reads extent, item type, and description before querying features. |
| Get features (`items`) | Tool | Parameterized query with bbox, limit, datetime, property filters. |
| Get feature by ID | Tool | Targeted lookup by identifier. |
| Spatial query (bbox) | Tool | Core spatial filtering — the LLM provides coordinates. |
| Queryables | Resource | Schema-level metadata about filterable properties. Stable. |
| Analysis workflow | Prompt | Multi-step template for discover → query → analyze. |

**Key decision:** Queryables are a **Resource**, not a Tool. Even though they require a GET request, queryables describe the *schema* of a collection — they define what queries are valid. The LLM reads this metadata to inform query construction, which is exactly the Resource pattern (context-providing, not action-performing).

### 4.3 OGC API — Records

Records extend Features with catalog-specific semantics. The mapping follows the same patterns with additions for full-text search and metadata-rich responses.

| OGC Concept | → MCP | Rationale |
|------------|-------|-----------|
| Catalog metadata | Resource | Describes what's discoverable — stable context. |
| Search records (`items?q=...`) | Tool | Active search with text, spatial, temporal, and type filters. |
| Get record by ID | Tool | Targeted metadata retrieval for a specific resource. |
| Discovery workflow | Prompt | Guides search → evaluate → select → access. |

**Key decision:** Records search is a **Tool** with a rich input schema that includes the `q` (full-text search) parameter from OGC Records. This is critical because it enables natural language to flow from the user through the LLM into the catalog search — the LLM extracts search terms from the user's request and passes them as the `q` parameter.

### 4.4 OGC API — EDR

EDR is the most diverse API with multiple query patterns. Each query pattern becomes its own MCP Tool because each requires different geometry input types.

| OGC Concept | → MCP | Rationale |
|------------|-------|-----------|
| EDR collection metadata | Resource | Parameter names, supported queries, extent — essential context. |
| Position query | Tool | Point-based sampling with WKT POINT. |
| Area query | Tool | Polygon-based sampling with WKT POLYGON. |
| Trajectory query | Tool | Path-based sampling with WKT LINESTRING. |
| Cube query | Tool | Bounding box subsetting — restricted polygon. |
| Radius query | Tool | Proximity-based sampling with point + distance. |
| Locations query | Tool | Named location listing — no coordinates needed. |
| Analysis workflow | Prompt | Pattern selection → geometry construction → result interpretation. |

**Key decision:** Each EDR query pattern is a **separate Tool** rather than one generic "edr_query" Tool. This is because each pattern requires fundamentally different geometry input (POINT vs POLYGON vs LINESTRING vs bbox), and the LLM makes better tool-calling decisions when tools have focused, specific purposes rather than generic multi-purpose interfaces.

**Key decision:** The EDR collection Resource includes the `parameter_names` and `data_queries` fields in its description. This is essential because the LLM must know *what* environmental parameters are available and *which* query patterns a specific collection supports before constructing a query.

### 4.5 OGC API — Processes

Processes have the most important mapping: **OGC Process → dynamically generated MCP Tool**.

| OGC Concept | → MCP | Rationale |
|------------|-------|-----------|
| Process description | Tool (dynamic) | **Each process becomes an independently callable MCP Tool with inputSchema derived from the OGC process description.** |
| Process list | Tool | Active discovery of available operations. |
| Execute process | Tool | The core action — submit inputs, trigger computation. |
| Job status | Tool | Async monitoring — poll until complete. |
| Job results | Tool | Retrieve computed output data. |
| Dismiss job | Tool | Cancel or clean up jobs. |
| Execution workflow | Prompt | The cool spot scenario: discover → configure → execute → retrieve → present. |

**Key decision:** The dynamic process-to-tool mapping (`process_as_tool`) is the most significant design choice in the entire specification. Instead of having a single generic `execute_process` tool, we also generate **individual MCP Tools** for each registered process. This means a server with a `geospatial-buffer` process and a `cool-spot-analysis` process exposes them as separate tools: `execute_geospatial_buffer` and `execute_cool_spot_analysis`, each with their own specific inputSchema. The LLM can then discover and understand each process independently, which dramatically improves tool selection accuracy.

## 5. URI Scheme Design

All MCP Resources use a consistent URI scheme:

```
ogc://{server_host}/collections/{collection_id}        # Features/Common
ogc://{server_host}/collections/{id}/queryables        # Queryables
ogc://{server_host}/catalogs/{catalog_id}              # Records
ogc://{server_host}/edr/{collection_id}                # EDR
```

The `ogc://` scheme is custom and meaningful — it signals to the MCP client that this resource originates from an OGC API server. The server host is encoded in the URI to enable multi-server scenarios where the LLM accesses data from different OGC backends simultaneously.

## 6. Modularity

The specification is deliberately modular:

- **Common** mappings are shared by all API types
- Each API type (Features, Records, EDR, Processes) has independent mappings
- New API types (Tiles, Maps, Coverages, Connected Systems) can be added without modifying existing mappings
- Each mapping rule is self-contained with its own rationale

This modularity matches the OGC API building blocks philosophy — just as OGC APIs are composed of reusable building blocks, our mappings are composed of reusable mapping rules.

## 7. Extensibility: OpenAPI Auto-Discovery

A critical architectural insight for the full GSoC implementation: every OGC API server MUST expose an OpenAPI definition at `/api`. This means the MCP server can **automatically parse that OpenAPI spec and generate MCP Tools dynamically**, making the system even more generic than a static JSON schema. The mapping specification defines the *rules* for how OGC concepts translate to MCP concepts; the runtime implementation can apply these rules to any OpenAPI definition it discovers.

## 8. Files in This Specification

| File | Purpose |
|------|---------|
| `ogc-mcp-mapping.schema.json` | **The meta-schema** — defines the structure of mapping rules. Validates that any OGC-to-MCP mapping follows the correct format. |
| `ogc-mcp-mapping-instance.json` | **The concrete mapping** — the actual populated mapping with every OGC concept translated to MCP, including rationale and field-level mappings. |
| `MAPPING_RATIONALE.md` | **This document** — explains the design decisions. |
| `mapping-summary.md` | **Quick reference** — a visual summary table of all mappings. |

## 9. Relationship to Existing Code

The `mapper.py` module in `src/ogc_mcp/` is the **runtime implementation** of this specification. Every function in mapper.py corresponds to a mapping rule in the JSON schema:

- `collection_to_resource()` → implements `features.collection_as_resource`
- `process_to_tool()` → implements `processes.process_as_tool`
- `build_discovery_tools()` → implements `common.landing_page`, `common.collections_list`
- `build_workflow_prompts()` → implements all `*_prompt` mappings

The specification is the formal definition; mapper.py is the executable code that brings it to life.
