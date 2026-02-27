"""
OGC-to-MCP Mapper — Translates OGC API objects into MCP protocol objects.

This is the intellectual core of the GSoC project. It implements the
formal mapping between OGC API concepts and MCP concepts:

    OGCCollection  →  MCP Resource  (data the LLM can read for context)
    OGCProcess     →  MCP Tool      (action the LLM can execute)
    OGCServerInfo  →  MCP Tool      (discovery the LLM can invoke)
    OGCRecord      →  MCP Resource  (catalog metadata for context)        ← NEW Stage 5
    OGCEDRCollection → MCP Resource (environmental data context)          ← NEW Stage 5

License: Apache Software License, Version 2.0
"""

import json
import mcp.types as types

try:
    from .ogc_client import (
        OGCCollection, OGCProcess, OGCServerInfo,
        OGCRecord, OGCEDRParameter, OGCEDRCollection,
    )
except ImportError:
    from ogc_mcp.ogc_client import (
        OGCCollection, OGCProcess, OGCServerInfo,
        OGCRecord, OGCEDRParameter, OGCEDRCollection,
    )


# ═══════════════════════════════════════════════════════════════
# OGC COLLECTION → MCP RESOURCE
# ═══════════════════════════════════════════════════════════════

def collection_to_resource(
    collection: OGCCollection,
    server_base_url: str
) -> types.Resource:
    """Map an OGC API Collection to an MCP Resource."""
    clean_base = server_base_url.rstrip("/").replace("://", "_").replace("/", "_")
    return types.Resource(
        uri=f"ogc://{clean_base}/collections/{collection.id}",
        name=collection.title,
        description=_build_collection_description(collection),
        mimeType="application/json"
    )


def _build_collection_description(collection: OGCCollection) -> str:
    """Build a rich description for a collection resource."""
    parts = [collection.description]
    if collection.extent:
        spatial = collection.extent.get("spatial", {})
        bbox = spatial.get("bbox", [])
        if bbox and len(bbox) > 0:
            b = bbox[0]
            if len(b) >= 4:
                parts.append(
                    f"Spatial extent: "
                    f"lon [{b[0]:.2f}, {b[2]:.2f}], "
                    f"lat [{b[1]:.2f}, {b[3]:.2f}]"
                )
    if collection.item_type:
        parts.append(f"Item type: {collection.item_type}")
    return " | ".join(p for p in parts if p)


# ═══════════════════════════════════════════════════════════════
# OGC PROCESS → MCP TOOL
# ═══════════════════════════════════════════════════════════════

def process_to_tool(
    process: OGCProcess,
    server_base_url: str
) -> types.Tool:
    """Map an OGC API Process to an MCP Tool."""
    input_schema = _build_process_input_schema(process, server_base_url)
    return types.Tool(
        name=f"execute_{process.id.replace('-', '_')}",
        description=_build_process_tool_description(process),
        inputSchema=input_schema
    )


def _build_process_tool_description(process: OGCProcess) -> str:
    parts = [
        f"Execute the '{process.title}' geospatial process.",
        process.description,
    ]
    if process.inputs:
        input_names = list(process.inputs.keys())
        parts.append(f"Required inputs: {', '.join(input_names)}.")
    return " ".join(p for p in parts if p)


def _build_process_input_schema(process: OGCProcess, server_base_url: str) -> dict:
    properties = {
        "server_url": {
            "type": "string",
            "description": "Base URL of the OGC API server.",
            "default": server_base_url
        },
    }
    for input_name, input_def in process.inputs.items():
        if isinstance(input_def, dict):
            schema = input_def.get("schema", {})
            prop = {"description": input_def.get("description", input_def.get("title", input_name))}
            if "type" in schema:
                prop["type"] = schema["type"]
            properties[input_name] = prop
    return {
        "type": "object",
        "properties": properties,
        "required": ["server_url"]
    }


# ═══════════════════════════════════════════════════════════════
# FORMAT FUNCTIONS — Convert OGC data to LLM-readable text
# ═══════════════════════════════════════════════════════════════

def format_server_info(info: OGCServerInfo) -> str:
    lines = [
        f"OGC Server: {info.title}",
        f"Description: {info.description}",
        f"Capabilities: {', '.join(info.capabilities)}",
    ]
    return "\n".join(lines)


def format_collections(collections: list[OGCCollection]) -> str:
    if not collections:
        return "No collections found on this server."
    lines = [f"Found {len(collections)} collections:", ""]
    for c in collections:
        item_type = f" (type: {c.item_type})" if c.item_type else ""
        lines.append(f"  [{c.id}] {c.title}{item_type}")
        if c.description:
            short = c.description[:100] + "..." if len(c.description) > 100 else c.description
            lines.append(f"    {short}")
    return "\n".join(lines)


def format_features(geojson: dict) -> str:
    features = geojson.get("features", [])
    if not features:
        return "No features found."
    matched = geojson.get("numberMatched", "unknown")
    returned = geojson.get("numberReturned", len(features))
    lines = [f"Retrieved {returned} features (total: {matched}):", ""]
    for f in features:
        props = f.get("properties", {})
        geom = f.get("geometry", {})
        geom_type = geom.get("type", "No geometry") if geom else "No geometry"
        name = props.get("name", props.get("title", f.get("id", "Unknown")))
        lines.append(f"  • {name} ({geom_type})")
        for k, v in list(props.items())[:5]:
            if k not in ("name", "title"):
                lines.append(f"    {k}: {v}")
    return "\n".join(lines)


def format_processes(processes: list[OGCProcess]) -> str:
    if not processes:
        return "No processes found on this server."
    lines = [f"Found {len(processes)} processes:", ""]
    for p in processes:
        lines.append(f"  [{p.id}] {p.title}")
        if p.description:
            short = p.description[:100] + "..." if len(p.description) > 100 else p.description
            lines.append(f"    {short}")
    return "\n".join(lines)


def format_process_detail(process: OGCProcess) -> str:
    lines = [
        f"Process: {process.title} (ID: {process.id})",
        f"Version: {process.version}",
        f"Description: {process.description}",
    ]
    if process.inputs:
        lines.append(f"Inputs: {list(process.inputs.keys())}")
        for name, inp in process.inputs.items():
            if isinstance(inp, dict):
                desc = inp.get("description", inp.get("title", ""))
                schema = inp.get("schema", {})
                inp_type = schema.get("type", "any")
                lines.append(f"  • {name} ({inp_type}): {desc}")
    if process.outputs:
        lines.append(f"Outputs: {list(process.outputs.keys())}")
    lines.append(f"Execution modes: {', '.join(process.job_control_options)}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# NEW Stage 5: OGC RECORDS FORMAT FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def format_catalog_records(geojson: dict) -> str:
    """Format OGC API Records search results for LLM consumption."""
    features = geojson.get("features", [])
    matched = geojson.get("numberMatched", "unknown")
    returned = geojson.get("numberReturned", len(features))

    if not features:
        return "No records found matching your search criteria."

    lines = [f"Found {returned} catalog records (total matching: {matched}):", ""]

    for i, feat in enumerate(features, 1):
        props = feat.get("properties", {})
        title = props.get("title", "Untitled")
        desc = props.get("description", "")
        record_type = props.get("type", "unknown")
        record_id = feat.get("id", "unknown")
        keywords = props.get("keywords", [])

        lines.append(f"  {i}. [{record_id}] {title}")
        lines.append(f"     Type: {record_type}")
        if desc:
            short = desc[:150] + "..." if len(desc) > 150 else desc
            lines.append(f"     Description: {short}")
        if keywords:
            lines.append(f"     Keywords: {', '.join(str(k) for k in keywords[:8])}")

        geom = feat.get("geometry")
        if geom and geom.get("coordinates"):
            lines.append(f"     Has spatial extent: Yes")
        lines.append("")

    return "\n".join(lines)


def format_catalog_record_detail(record: OGCRecord) -> str:
    """Format a single OGC API Records entry in detail."""
    lines = [
        f"Record: {record.title}",
        f"ID: {record.id}",
        f"Type: {record.type}",
    ]
    if record.description:
        lines.append(f"Description: {record.description}")
    if record.keywords:
        lines.append(f"Keywords: {', '.join(str(k) for k in record.keywords)}")
    if record.bbox:
        b = record.bbox
        lines.append(f"Spatial extent: lon [{b[0]:.2f}, {b[2]:.2f}], lat [{b[1]:.2f}, {b[3]:.2f}]")
    if record.created:
        lines.append(f"Created: {record.created}")
    if record.updated:
        lines.append(f"Updated: {record.updated}")
    for link in record.links:
        rel = link.get("rel", "")
        if rel in ("enclosure", "canonical", "describedby", "service"):
            lines.append(f"Link ({rel}): {link.get('href', '')}")
    return "\n".join(lines)


def record_to_resource(record: OGCRecord, server_base_url: str) -> types.Resource:
    """Map an OGC API Record to an MCP Resource."""
    clean_base = server_base_url.rstrip("/").replace("://", "_").replace("/", "_")
    desc_parts = [record.description]
    if record.keywords:
        desc_parts.append(f"Keywords: {', '.join(str(k) for k in record.keywords[:5])}")
    return types.Resource(
        uri=f"ogc://{clean_base}/records/{record.id}",
        name=record.title,
        description=" | ".join(p for p in desc_parts if p),
        mimeType="application/json"
    )


# ═══════════════════════════════════════════════════════════════
# NEW Stage 5: OGC EDR FORMAT FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def format_edr_collection(edr_collection: OGCEDRCollection) -> str:
    """Format an EDR collection's metadata for LLM consumption."""
    lines = [
        f"EDR Collection: {edr_collection.title}",
        f"ID: {edr_collection.id}",
    ]
    if edr_collection.description:
        lines.append(f"Description: {edr_collection.description}")

    if edr_collection.parameters:
        lines.append("")
        lines.append(f"Available parameters ({len(edr_collection.parameters)}):")
        for param in edr_collection.parameters:
            unit_str = f" ({param.unit})" if param.unit else ""
            lines.append(f"  • {param.id}: {param.label}{unit_str}")
            if param.description:
                lines.append(f"    {param.description[:100]}")

    if edr_collection.query_types:
        lines.append("")
        lines.append(f"Supported query types: {', '.join(edr_collection.query_types)}")
        query_help = {
            "position": "Point-based sampling (POINT geometry)",
            "area": "Polygon-based sampling (POLYGON geometry)",
            "cube": "Bounding box subsetting",
            "trajectory": "Path-based sampling (LINESTRING geometry)",
            "radius": "Proximity sampling (point + distance)",
        }
        for qt in edr_collection.query_types:
            if qt in query_help:
                lines.append(f"  • {qt}: {query_help[qt]}")

    if edr_collection.extent:
        spatial = edr_collection.extent.get("spatial", {})
        bbox = spatial.get("bbox", [])
        if bbox and len(bbox) > 0 and len(bbox[0]) >= 4:
            b = bbox[0]
            lines.append(f"")
            lines.append(f"Spatial extent: lon [{b[0]:.2f}, {b[2]:.2f}], lat [{b[1]:.2f}, {b[3]:.2f}]")
        temporal = edr_collection.extent.get("temporal", {})
        interval = temporal.get("interval", [])
        if interval and len(interval) > 0:
            t = interval[0]
            lines.append(f"Temporal extent: {t[0]} to {t[1]}")

    return "\n".join(lines)


def format_edr_query_result(result: dict, query_type: str = "position") -> str:
    """Format an EDR query result (CoverageJSON/JSON) for LLM consumption."""
    # Safety: if result is somehow a string, try to parse it
    if isinstance(result, str):
        try:
            import json as _json
            result = _json.loads(result)
        except Exception:
            return f"EDR {query_type} query returned raw text response."
    if not isinstance(result, dict):
        return f"EDR {query_type} query returned unexpected format: {type(result).__name__}"

    result_type = result.get("type", "unknown")

    # CoverageJSON
    if result_type == "Coverage" or "ranges" in result or "domain" in result:
        return _format_coverage_json(result, query_type)

    # GeoJSON
    if result_type == "FeatureCollection" or "features" in result:
        features = result.get("features", [])
        return f"EDR {query_type} query returned {len(features)} features as GeoJSON."

    # Fallback
    lines = [f"EDR {query_type} query result:"]
    for key in ("type", "domain", "ranges", "parameters"):
        if key in result:
            lines.append(f"  {key}: present")
    if len(lines) == 1:
        lines.append(f"  Response keys: {', '.join(list(result.keys())[:10])}")
    return "\n".join(lines)


def _format_coverage_json(covjson: dict, query_type: str) -> str:
    """Parse and format a CoverageJSON response."""
    lines = [f"EDR {query_type} query results (CoverageJSON):"]

    try:
        domain = covjson.get("domain", {})
        if isinstance(domain, dict):
            axes = domain.get("axes", {})
            if isinstance(axes, dict):
                if "x" in axes and "y" in axes:
                    x_ax = axes["x"]
                    y_ax = axes["y"]
                    if isinstance(x_ax, dict) and isinstance(y_ax, dict):
                        x_vals = x_ax.get("values", [])
                        y_vals = y_ax.get("values", [])
                        if x_vals and y_vals:
                            lines.append(f"  Location: lon={x_vals[0]}, lat={y_vals[0]}")

                if "t" in axes:
                    t_ax = axes["t"]
                    if isinstance(t_ax, dict):
                        t_vals = t_ax.get("values", [])
                        if t_vals:
                            if len(t_vals) == 1:
                                lines.append(f"  Time: {t_vals[0]}")
                            else:
                                lines.append(f"  Time range: {t_vals[0]} to {t_vals[-1]} ({len(t_vals)} steps)")

        ranges = covjson.get("ranges", {})
        parameters = covjson.get("parameters", {})
        if not isinstance(ranges, dict):
            ranges = {}
        if not isinstance(parameters, dict):
            parameters = {}

        if ranges:
            lines.append("")
            lines.append("  Parameter values:")
            for param_name, range_data in ranges.items():
                if isinstance(range_data, str):
                    lines.append(f"    {param_name}: {range_data}")
                    continue

                values = range_data.get("values", [])
                param_info = parameters.get(param_name, {})
                if isinstance(param_info, str):
                    label = param_info
                    unit = ""
                else:
                    obs_prop = param_info.get("observedProperty", {})
                    if isinstance(obs_prop, str):
                        label = obs_prop
                    elif isinstance(obs_prop, dict):
                        label = obs_prop.get("label", param_name)
                    else:
                        label = param_name

                    unit_info = param_info.get("unit", {})
                    unit = ""
                    if isinstance(unit_info, str):
                        unit = unit_info
                    elif isinstance(unit_info, dict):
                        symbol = unit_info.get("symbol", "")
                        if isinstance(symbol, dict):
                            unit = symbol.get("value", unit_info.get("label", ""))
                        elif isinstance(symbol, str):
                            unit = symbol or unit_info.get("label", "")

                unit_str = f" {unit}" if unit else ""

                real_values = [v for v in values if v is not None]
                if not real_values:
                    lines.append(f"    {label} ({param_name}): no data at this location")
                elif len(real_values) == 1:
                    lines.append(f"    {label} ({param_name}): {real_values[0]}{unit_str}")
                else:
                    avg = sum(real_values) / len(real_values)
                    mn, mx = min(real_values), max(real_values)
                    lines.append(
                        f"    {label} ({param_name}): "
                        f"avg={avg:.2f}{unit_str}, min={mn:.2f}, max={mx:.2f} "
                        f"({len(real_values)} values)"
                    )
        else:
            lines.append("  No parameter data in response.")

    except Exception as e:
        lines.append(f"  Error parsing CoverageJSON: {type(e).__name__}: {e}")

    return "\n".join(lines)


def edr_collection_to_resource(edr_collection: OGCEDRCollection, server_base_url: str) -> types.Resource:
    """Map an OGC API EDR collection to an MCP Resource."""
    clean_base = server_base_url.rstrip("/").replace("://", "_").replace("/", "_")
    desc_parts = [edr_collection.description]
    if edr_collection.parameters:
        desc_parts.append(f"Parameters: {', '.join(p.id for p in edr_collection.parameters)}")
    if edr_collection.query_types:
        desc_parts.append(f"Queries: {', '.join(edr_collection.query_types)}")
    return types.Resource(
        uri=f"ogc://{clean_base}/edr/{edr_collection.id}",
        name=edr_collection.title,
        description=" | ".join(p for p in desc_parts if p),
        mimeType="application/json"
    )


# ═══════════════════════════════════════════════════════════════
# MCP TOOL DEFINITIONS — All tools the server registers
# ═══════════════════════════════════════════════════════════════

def build_discovery_tools() -> list[types.Tool]:
    """Build the complete list of MCP Tools for OGC API operations."""
    tools = [
        # ── Common ──────────────────────────────
        types.Tool(
            name="discover_ogc_server",
            description=(
                "Discover an OGC API server's capabilities. "
                "Returns the server title, description, and which API types "
                "it supports (Features, Processes, Records, EDR). "
                "Always call this first when connecting to a new server."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {
                        "type": "string",
                        "description": "Base URL of the OGC API server."
                    }
                },
                "required": ["server_url"]
            }
        ),
        types.Tool(
            name="get_collections",
            description=(
                "List all data collections available on an OGC API server. "
                "Returns collection IDs, titles, descriptions, and item types. "
                "Look for itemType='record' to find catalog collections (Records API) "
                "and check for EDR collections with parameter_names."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {
                        "type": "string",
                        "description": "Base URL of the OGC API server."
                    }
                },
                "required": ["server_url"]
            }
        ),
        types.Tool(
            name="get_collection_detail",
            description=(
                "Get detailed metadata for a specific collection including "
                "spatial/temporal extent, item type, and available links. "
                "Use before get_features() to understand the collection."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {
                        "type": "string",
                        "description": "Base URL of the OGC API server."
                    },
                    "collection_id": {
                        "type": "string",
                        "description": "Collection ID from get_collections()."
                    }
                },
                "required": ["server_url", "collection_id"]
            }
        ),

        # ── Features ────────────────────────────
        types.Tool(
            name="get_features",
            description=(
                "Fetch geographic features from a collection as GeoJSON. "
                "Supports spatial filtering by bounding box, temporal filtering, "
                "and attribute filtering via CQL2."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {
                        "type": "string",
                        "description": "Base URL of the OGC API server."
                    },
                    "collection_id": {
                        "type": "string",
                        "description": "Collection to query."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max features to return. Default: 10.",
                        "default": 10
                    },
                    "bbox": {
                        "type": "string",
                        "description": "Bounding box: 'minLon,minLat,maxLon,maxLat'"
                    },
                    "datetime": {
                        "type": "string",
                        "description": "Temporal filter (ISO 8601 instant or interval)."
                    },
                    "filter_cql": {
                        "type": "string",
                        "description": "CQL2 attribute filter expression."
                    }
                },
                "required": ["server_url", "collection_id"]
            }
        ),

        # ── Processes ───────────────────────────
        types.Tool(
            name="discover_processes",
            description="List all geospatial analysis processes available on an OGC API server.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {"type": "string", "description": "Base URL of the OGC API server."}
                },
                "required": ["server_url"]
            }
        ),
        types.Tool(
            name="get_process_detail",
            description="Get full details for a process including input schema. Call before execute_process().",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {"type": "string", "description": "Base URL of the OGC API server."},
                    "process_id": {"type": "string", "description": "Process ID from discover_processes()."}
                },
                "required": ["server_url", "process_id"]
            }
        ),
        types.Tool(
            name="execute_process",
            description="Execute a geospatial process with given inputs. Returns results directly (sync) or a job ID (async).",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {"type": "string", "description": "Base URL of the OGC API server."},
                    "process_id": {"type": "string", "description": "Process ID to execute."},
                    "inputs": {"type": "object", "description": "Input parameters matching the process schema."},
                    "async_execute": {"type": "boolean", "description": "If true, return job ID for async monitoring.", "default": False}
                },
                "required": ["server_url", "process_id", "inputs"]
            }
        ),
        types.Tool(
            name="get_job_status",
            description="Check the status of an asynchronous process job.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {"type": "string", "description": "Base URL of the OGC API server."},
                    "job_id": {"type": "string", "description": "Job ID from execute_process()."}
                },
                "required": ["server_url", "job_id"]
            }
        ),
        types.Tool(
            name="get_job_results",
            description="Retrieve the results of a completed process job.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {"type": "string", "description": "Base URL of the OGC API server."},
                    "job_id": {"type": "string", "description": "Job ID from execute_process()."}
                },
                "required": ["server_url", "job_id"]
            }
        ),

        # ═══ NEW Stage 5: Records Tools ═════════

        types.Tool(
            name="search_catalog",
            description=(
                "Search an OGC API Records catalog for geospatial datasets. "
                "Supports full-text search (q parameter), spatial bounding box, "
                "and temporal filtering. Requires the catalog collection ID — "
                "identify them with get_collections() (look for itemType='record')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {"type": "string", "description": "Base URL of the OGC API server."},
                    "catalog_id": {
                        "type": "string",
                        "description": "ID of the records/catalog collection (itemType='record')."
                    },
                    "q": {
                        "type": "string",
                        "description": "Full-text search terms. Example: 'biomassa' or 'water quality'"
                    },
                    "bbox": {"type": "string", "description": "Spatial filter: 'minLon,minLat,maxLon,maxLat'"},
                    "datetime": {"type": "string", "description": "Temporal filter."},
                    "limit": {"type": "integer", "description": "Max records. Default: 10.", "default": 10}
                },
                "required": ["server_url", "catalog_id"]
            }
        ),
        types.Tool(
            name="get_catalog_record",
            description=(
                "Get full metadata for a specific catalog record by ID. "
                "Returns title, description, type, keywords, spatial extent, and access links."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {"type": "string", "description": "Base URL of the OGC API server."},
                    "catalog_id": {"type": "string", "description": "ID of the catalog collection."},
                    "record_id": {"type": "string", "description": "Unique record identifier."}
                },
                "required": ["server_url", "catalog_id", "record_id"]
            }
        ),

        # ═══ NEW Stage 5: EDR Tools ═════════════

        types.Tool(
            name="query_edr_position",
            description=(
                "Query environmental data at a specific geographic point. "
                "Returns parameter values (temperature, wind, etc.) at given coordinates. "
                "Use get_collections() to find EDR collections with parameter_names."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {"type": "string", "description": "Base URL of the OGC API server."},
                    "collection_id": {"type": "string", "description": "EDR collection ID (e.g., 'icoads-sst')."},
                    "coords": {
                        "type": "string",
                        "description": "WKT POINT: 'POINT(longitude latitude)'. Example: 'POINT(33 33)'"
                    },
                    "parameter_name": {
                        "type": "string",
                        "description": "Comma-separated parameters. Example: 'SST' or 'SST,AIRT'. Omit for all."
                    },
                    "datetime": {"type": "string", "description": "Temporal filter. Example: '2000-04-16'"}
                },
                "required": ["server_url", "collection_id", "coords"]
            }
        ),
        types.Tool(
            name="query_edr_area",
            description=(
                "Query environmental data within a polygon area. "
                "Returns parameter values for all data points within the polygon."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {"type": "string", "description": "Base URL of the OGC API server."},
                    "collection_id": {"type": "string", "description": "EDR collection ID."},
                    "coords": {
                        "type": "string",
                        "description": "WKT POLYGON: 'POLYGON((lon1 lat1, lon2 lat2, ...))'. Must be closed."
                    },
                    "parameter_name": {"type": "string", "description": "Comma-separated parameters."},
                    "datetime": {"type": "string", "description": "Temporal filter."}
                },
                "required": ["server_url", "collection_id", "coords"]
            }
        ),
    ]
    return tools


# ═══════════════════════════════════════════════════════════════
# WORKFLOW PROMPTS
# ═══════════════════════════════════════════════════════════════

def build_workflow_prompts() -> list[types.Prompt]:
    return [
        types.Prompt(
            name="spatial_analysis_workflow",
            description="Step-by-step workflow for spatial data analysis using OGC API Features.",
            arguments=[
                types.PromptArgument(name="server_url", description="OGC API server URL", required=True),
                types.PromptArgument(name="analysis_goal", description="What to analyze", required=True),
            ]
        ),
        types.Prompt(
            name="process_execution_workflow",
            description="Workflow for discovering and executing OGC API Processes (like cool spot analysis).",
            arguments=[
                types.PromptArgument(name="server_url", description="OGC API server URL", required=True),
                types.PromptArgument(name="analysis_goal", description="What to analyze", required=True),
            ]
        ),
        types.Prompt(
            name="data_discovery_workflow",
            description="Workflow for discovering geospatial datasets via OGC API Records catalog search.",
            arguments=[
                types.PromptArgument(name="server_url", description="OGC API server URL", required=True),
                types.PromptArgument(name="analysis_goal", description="What data to find", required=True),
            ]
        ),
    ]
