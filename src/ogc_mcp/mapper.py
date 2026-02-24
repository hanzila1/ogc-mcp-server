"""
OGC-to-MCP Mapper — Translates OGC API objects into MCP protocol objects.

This is the intellectual core of the GSoC project. It implements the
formal mapping between OGC API concepts and MCP concepts:

    OGCCollection  →  MCP Resource  (data the LLM can read for context)
    OGCProcess     →  MCP Tool      (action the LLM can execute)
    OGCServerInfo  →  MCP Tool      (discovery the LLM can invoke)

The mapping is designed to be:
    - Generic:     Works for any OGC-compliant server, not just one instance
    - Extensible:  New OGC API types can be added without changing core logic
    - Faithful:    Preserves all semantic meaning from the OGC specification

License: Apache Software License, Version 2.0
"""

import json
import mcp.types as types
from .ogc_client import OGCCollection, OGCProcess, OGCServerInfo


# ═══════════════════════════════════════════════════════════════
# OGC COLLECTION → MCP RESOURCE
# Collections are read-only data sources — they map to MCP Resources.
# The URI scheme is: ogc://{server_base_url}/collections/{collection_id}
# ═══════════════════════════════════════════════════════════════

def collection_to_resource(
    collection: OGCCollection,
    server_base_url: str
) -> types.Resource:
    """
    Map an OGC API Collection to an MCP Resource.

    MCP Resources are identified by URI and represent data the LLM
    can read for context. A collection's metadata — its title,
    description, spatial extent, and schema — becomes a Resource
    the LLM reads before querying features from it.

    URI scheme: ogc://{server_base_url}/collections/{collection_id}

    Args:
        collection:      The OGC collection to map.
        server_base_url: Base URL of the originating server.
                         Used to construct the Resource URI.

    Returns:
        MCP Resource object the server can expose to LLM clients.
    """
    # Normalize the base URL for use in URIs
    clean_base = server_base_url.rstrip("/").replace("://", "_").replace("/", "_")

    return types.Resource(
        uri=f"ogc://{clean_base}/collections/{collection.id}",
        name=collection.title,
        description=_build_collection_description(collection),
        mimeType="application/json"
    )


def _build_collection_description(collection: OGCCollection) -> str:
    """Build a rich, informative description for a collection resource."""
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
# Processes are executable operations — they map directly to MCP Tools.
# The MCP Tool's inputSchema is derived from the OGC process input schema.
# ═══════════════════════════════════════════════════════════════

def process_to_tool(
    process: OGCProcess,
    server_base_url: str
) -> types.Tool:
    """
    Map an OGC API Process to an MCP Tool.

    This is the most important mapping in the project. An OGC process
    has a formal JSON Schema describing its inputs — we translate that
    directly into the MCP Tool's inputSchema. The LLM reads the Tool's
    name, description, and inputSchema to understand what to call and
    with what parameters.

    The inputSchema is extended with a "server_url" parameter so the
    LLM can target any OGC server, not just the discovery server.

    Args:
        process:         The OGC process to map.
        server_base_url: Default server URL (used as default in schema).

    Returns:
        MCP Tool object with name, description, and full inputSchema.
    """
    input_schema = _build_process_input_schema(process, server_base_url)

    return types.Tool(
        name=f"execute_{process.id.replace('-', '_')}",
        description=_build_process_tool_description(process),
        inputSchema=input_schema
    )


def _build_process_tool_description(process: OGCProcess) -> str:
    """
    Build a rich tool description that helps the LLM understand
    when and how to use this process tool.
    """
    parts = [
        f"Execute the '{process.title}' geospatial process.",
        process.description,
    ]

    if process.inputs:
        input_names = list(process.inputs.keys())
        parts.append(f"Required inputs: {', '.join(input_names)}.")

    if process.outputs:
        output_names = list(process.outputs.keys())
        parts.append(f"Produces outputs: {', '.join(output_names)}.")

    exec_modes = []
    if "sync-execute" in process.job_control_options:
        exec_modes.append("synchronous (immediate result)")
    if "async-execute" in process.job_control_options:
        exec_modes.append("asynchronous (returns job ID)")
    if exec_modes:
        parts.append(f"Execution modes: {', '.join(exec_modes)}.")

    if process.keywords:
        parts.append(f"Keywords: {', '.join(process.keywords)}.")

    return " ".join(parts)


def _build_process_input_schema(
    process: OGCProcess,
    server_base_url: str
) -> dict:
    """
    Build a JSON Schema dict for the MCP Tool inputSchema by
    translating OGC process inputs into JSON Schema properties.

    The OGC process input schema uses a nested structure:
        {
          "input_name": {
            "title": "...",
            "description": "...",
            "schema": {"type": "string"}
          }
        }

    We flatten this into a standard JSON Schema object:
        {
          "type": "object",
          "properties": {
            "server_url": {"type": "string", ...},
            "input_name": {"type": "string", ...}
          },
          "required": ["server_url", "input_name"]
        }
    """
    properties = {
        # Every process tool accepts a server_url so the LLM
        # can target different OGC servers dynamically
        "server_url": {
            "type": "string",
            "description": (
                "Base URL of the OGC API server to execute this process on. "
                f"Default: {server_base_url}"
            ),
            "default": server_base_url
        }
    }
    required = ["server_url"]

    for input_name, input_def in process.inputs.items():
        # Extract the JSON schema from the OGC input definition
        ogc_schema = input_def.get("schema", {})

        prop = {
            "description": input_def.get(
                "description",
                input_def.get("title", f"Input: {input_name}")
            )
        }

        # Map OGC schema type to JSON Schema type
        ogc_type = ogc_schema.get("type", "string")
        if ogc_type in ("string", "number", "integer", "boolean", "array", "object"):
            prop["type"] = ogc_type
        else:
            prop["type"] = "string"

        # Preserve enum values if present
        if "enum" in ogc_schema:
            prop["enum"] = ogc_schema["enum"]

        # Preserve format hints (e.g. "uri", "date-time")
        if "format" in ogc_schema:
            prop["format"] = ogc_schema["format"]

        # Preserve array item schemas
        if ogc_type == "array" and "items" in ogc_schema:
            prop["items"] = ogc_schema["items"]

        properties[input_name] = prop

        # Mark as required if minOccurs > 0 (default in OGC spec)
        min_occurs = input_def.get("minOccurs", 1)
        if min_occurs > 0:
            required.append(input_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required
    }


# ═══════════════════════════════════════════════════════════════
# BUILT-IN DISCOVERY TOOLS
# These tools are always registered regardless of what a specific
# server offers. They give the LLM the ability to explore any
# OGC server dynamically.
# ═══════════════════════════════════════════════════════════════

def build_discovery_tools() -> list[types.Tool]:
    """
    Build the set of built-in discovery and data access tools.

    These tools are always available on the MCP server regardless of
    which OGC backend is connected. They enable the LLM to:
    1. Explore what any OGC server offers
    2. Query feature data from any collection
    3. Search records/catalog
    4. Discover and execute any process

    Returns:
        List of MCP Tool objects for core OGC capabilities.
    """
    return [
        _build_discover_server_tool(),
        _build_get_collections_tool(),
        _build_get_features_tool(),
        _build_get_collection_detail_tool(),
        _build_discover_processes_tool(),
        _build_get_process_detail_tool(),
        _build_execute_process_tool(),
        _build_get_job_status_tool(),
        _build_get_job_results_tool(),
    ]


def _build_discover_server_tool() -> types.Tool:
    return types.Tool(
        name="discover_ogc_server",
        description=(
            "Discover the capabilities of any OGC API-compliant geospatial server. "
            "Returns the server's title, description, and a list of supported "
            "capabilities (features, processes, tiles, etc.). "
            "Use this as the FIRST call when connecting to a new OGC server to "
            "understand what it offers before making more specific requests."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "server_url": {
                    "type": "string",
                    "description": (
                        "Base URL of the OGC API server to explore. "
                        "Example: 'https://demo.pygeoapi.io/master'"
                    )
                }
            },
            "required": ["server_url"]
        }
    )


def _build_get_collections_tool() -> types.Tool:
    return types.Tool(
        name="get_collections",
        description=(
            "List all available geospatial datasets (collections) on an OGC API server. "
            "Returns each collection's ID, title, and description. "
            "Use the returned collection IDs with get_features() to fetch actual data. "
            "Call this to answer questions like 'what data is available?' or "
            "'does this server have flood risk data?'"
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
    )


def _build_get_collection_detail_tool() -> types.Tool:
    return types.Tool(
        name="get_collection_detail",
        description=(
            "Get detailed metadata for a specific geospatial collection including "
            "its spatial extent, coordinate reference system, and available properties. "
            "Use before get_features() to understand the collection's coverage area "
            "and what filtering options are available."
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
                    "description": (
                        "The collection identifier. "
                        "Get valid IDs from get_collections()."
                    )
                }
            },
            "required": ["server_url", "collection_id"]
        }
    )


def _build_get_features_tool() -> types.Tool:
    return types.Tool(
        name="get_features",
        description=(
            "Fetch geographic features (points, lines, polygons) from a collection "
            "as GeoJSON. Supports spatial filtering by bounding box, temporal filtering "
            "by date/time, and attribute filtering using CQL2 expressions. "
            "Returns a GeoJSON FeatureCollection with geometry and properties. "
            "Examples: get all lakes in Europe, find buildings built after 2000, "
            "retrieve flood zones intersecting a municipality boundary."
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
                    "description": "The collection to query. Get IDs from get_collections()."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of features to return. Default: 10.",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 10000
                },
                "bbox": {
                    "type": "string",
                    "description": (
                        "Bounding box spatial filter in WGS84. "
                        "Format: 'minLon,minLat,maxLon,maxLat'. "
                        "Example: '-10,35,40,75' filters to Europe. "
                        "Example: '6.5,51.0,8.0,52.5' filters to NRW, Germany."
                    )
                },
                "datetime": {
                    "type": "string",
                    "description": (
                        "Temporal filter in ISO 8601. "
                        "Instant: '2024-06-01T00:00:00Z'. "
                        "Interval: '2024-01-01/2024-12-31'. "
                        "Open end: '2024-01-01/..'"
                    )
                },
                "filter_cql": {
                    "type": "string",
                    "description": (
                        "CQL2 attribute filter expression. "
                        "Example: \"population > 1000000\" "
                        "Example: \"name LIKE 'Lake%'\""
                    )
                }
            },
            "required": ["server_url", "collection_id"]
        }
    )


def _build_discover_processes_tool() -> types.Tool:
    return types.Tool(
        name="discover_processes",
        description=(
            "List all geospatial analysis processes available on an OGC API server. "
            "Returns each process's ID, title, and description. "
            "Use this to answer questions like 'what analyses can this server run?' "
            "or 'is there a buffer or cool spot analysis available?' "
            "Use the returned process IDs with get_process_detail() and execute_process()."
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
    )


def _build_get_process_detail_tool() -> types.Tool:
    return types.Tool(
        name="get_process_detail",
        description=(
            "Get full details for a specific geospatial process including its "
            "complete input parameter schema and expected output format. "
            "Always call this BEFORE execute_process() to understand exactly "
            "what inputs are required and their correct format. "
            "This lets you pre-fill parameters or ask the user for missing inputs."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "server_url": {
                    "type": "string",
                    "description": "Base URL of the OGC API server."
                },
                "process_id": {
                    "type": "string",
                    "description": (
                        "The process identifier. "
                        "Get valid IDs from discover_processes()."
                    )
                }
            },
            "required": ["server_url", "process_id"]
        }
    )


def _build_execute_process_tool() -> types.Tool:
    return types.Tool(
        name="execute_process",
        description=(
            "Execute any geospatial process on an OGC API server. "
            "Supports both synchronous execution (waits for result) and "
            "asynchronous execution (returns job ID immediately for long processes). "
            "Always call get_process_detail() first to understand required inputs. "
            "For async jobs, use get_job_status() to monitor progress and "
            "get_job_results() to retrieve the final output."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "server_url": {
                    "type": "string",
                    "description": "Base URL of the OGC API server."
                },
                "process_id": {
                    "type": "string",
                    "description": "The process to execute."
                },
                "inputs": {
                    "type": "object",
                    "description": (
                        "Input parameters as a JSON object. "
                        "Keys and value types must match the process input schema "
                        "from get_process_detail()."
                    )
                },
                "async_execute": {
                    "type": "boolean",
                    "description": (
                        "If true, execute asynchronously and return a job ID. "
                        "Use for long-running analyses. Default: false."
                    ),
                    "default": False
                }
            },
            "required": ["server_url", "process_id", "inputs"]
        }
    )


def _build_get_job_status_tool() -> types.Tool:
    return types.Tool(
        name="get_job_status",
        description=(
            "Check the status of an asynchronous geospatial processing job. "
            "Returns status: 'accepted', 'running', 'successful', 'failed', or 'dismissed'. "
            "Poll this periodically after async execute_process() until status is "
            "'successful', then call get_job_results() to retrieve the output."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "server_url": {
                    "type": "string",
                    "description": "Base URL of the OGC API server."
                },
                "job_id": {
                    "type": "string",
                    "description": "Job identifier returned by async execute_process()."
                }
            },
            "required": ["server_url", "job_id"]
        }
    )


def _build_get_job_results_tool() -> types.Tool:
    return types.Tool(
        name="get_job_results",
        description=(
            "Retrieve the output of a successfully completed async processing job. "
            "Only call this after get_job_status() returns status='successful'. "
            "Returns the process output data — typically GeoJSON, statistics, "
            "or other geospatial analysis results."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "server_url": {
                    "type": "string",
                    "description": "Base URL of the OGC API server."
                },
                "job_id": {
                    "type": "string",
                    "description": "Job identifier of a completed job."
                }
            },
            "required": ["server_url", "job_id"]
        }
    )


# ═══════════════════════════════════════════════════════════════
# WORKFLOW PROMPTS
# Generic workflow templates — NOT hardcoded to cool spots.
# These guide the LLM through multi-step OGC API operations.
# ═══════════════════════════════════════════════════════════════

def build_workflow_prompts() -> list[types.Prompt]:
    """
    Build generic workflow prompt templates for common OGC operations.

    These prompts guide an LLM through multi-step geospatial workflows
    in a structured, reliable way. They are deliberately generic —
    any specific analysis (cool spot, buffer, intersection, etc.)
    is handled as a parameterized instance of these templates.
    """
    return [
        types.Prompt(
            name="spatial_analysis_workflow",
            description=(
                "Guide the LLM through a complete spatial analysis workflow: "
                "discover available processes → understand required inputs → "
                "validate user data → execute process → monitor job → "
                "retrieve and present results. Works for ANY OGC API process."
            ),
            arguments=[
                types.PromptArgument(
                    name="server_url",
                    description="OGC API server URL",
                    required=True
                ),
                types.PromptArgument(
                    name="analysis_goal",
                    description="Natural language description of what the user wants to analyse",
                    required=True
                ),
                types.PromptArgument(
                    name="user_data_description",
                    description="Description of the input data the user has available",
                    required=False
                )
            ]
        ),
        types.Prompt(
            name="data_discovery_workflow",
            description=(
                "Guide the LLM through discovering and fetching relevant geospatial data: "
                "explore available collections → filter by topic/location/time → "
                "fetch matching features → summarize results. "
                "Works for any OGC API - Features or Records server."
            ),
            arguments=[
                types.PromptArgument(
                    name="server_url",
                    description="OGC API server URL",
                    required=True
                ),
                types.PromptArgument(
                    name="data_need",
                    description="What data the user is looking for",
                    required=True
                ),
                types.PromptArgument(
                    name="area_of_interest",
                    description="Geographic area of interest (city, country, or bbox)",
                    required=False
                )
            ]
        ),
        types.Prompt(
            name="server_exploration_workflow",
            description=(
                "Guide the LLM through fully exploring an unknown OGC API server: "
                "check capabilities → list all collections → list all processes → "
                "summarize what the server offers in plain language."
            ),
            arguments=[
                types.PromptArgument(
                    name="server_url",
                    description="OGC API server URL to explore",
                    required=True
                )
            ]
        )
    ]


# ═══════════════════════════════════════════════════════════════
# RESPONSE FORMATTERS
# Convert OGC API responses into clean text for LLM consumption.
# ═══════════════════════════════════════════════════════════════

def format_server_info(info: OGCServerInfo) -> str:
    """Format OGCServerInfo as readable text for LLM response."""
    lines = [
        f"OGC Server: {info.title}",
        f"URL: {info.base_url}",
    ]
    if info.description:
        lines.append(f"Description: {info.description}")
    if info.capabilities:
        lines.append(f"Capabilities: {', '.join(info.capabilities)}")
    return "\n".join(lines)


def format_collections(collections: list[OGCCollection]) -> str:
    """Format a list of collections as readable text for LLM response."""
    if not collections:
        return "No collections found on this server."
    lines = [f"Found {len(collections)} collections:"]
    for col in collections:
        lines.append(f"\n  [{col.id}] {col.title}")
        if col.description and col.description != "No description available.":
            lines.append(f"    {col.description[:120]}")
    return "\n".join(lines)


def format_processes(processes: list[OGCProcess]) -> str:
    """Format a list of processes as readable text for LLM response."""
    if not processes:
        return "No processes found on this server."
    lines = [f"Found {len(processes)} available processes:"]
    for proc in processes:
        lines.append(f"\n  [{proc.id}] {proc.title}")
        if proc.description and proc.description != "No description available.":
            lines.append(f"    {proc.description[:120]}")
        if proc.inputs:
            lines.append(f"    Inputs: {', '.join(proc.inputs.keys())}")
    return "\n".join(lines)


def format_features(geojson: dict) -> str:
    """Format a GeoJSON FeatureCollection as readable text for LLM response."""
    features = geojson.get("features", [])
    total = geojson.get("numberMatched", len(features))
    returned = geojson.get("numberReturned", len(features))

    lines = [f"Retrieved {returned} features (total matching: {total}):"]
    for i, feature in enumerate(features, 1):
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        geom_type = geom.get("type", "Unknown") if geom else "No geometry"

        name = (props.get("name") or
                props.get("title") or
                props.get("id") or
                feature.get("id") or
                f"Feature {i}")

        lines.append(f"\n  {i}. {name} ({geom_type})")
        for key, value in list(props.items())[:4]:
            if key not in ("name", "title") and value is not None:
                lines.append(f"     {key}: {value}")

    return "\n".join(lines)


def format_process_detail(process: OGCProcess) -> str:
    """Format full process detail as readable text for LLM response."""
    lines = [
        f"Process: {process.title} (ID: {process.id})",
        f"Version: {process.version}",
        f"Description: {process.description}",
        "",
        "Required Inputs:"
    ]
    for name, defn in process.inputs.items():
        schema = defn.get("schema", {})
        ptype = schema.get("type", "string")
        desc = defn.get("description", defn.get("title", ""))
        min_occ = defn.get("minOccurs", 1)
        required_str = "required" if min_occ > 0 else "optional"
        lines.append(f"  - {name} ({ptype}, {required_str}): {desc}")

    lines.append("")
    lines.append("Outputs:")
    for name, defn in process.outputs.items():
        schema = defn.get("schema", {})
        ptype = schema.get("type", "object")
        lines.append(f"  - {name} ({ptype})")

    modes = ", ".join(process.job_control_options)
    lines.append(f"\nExecution modes: {modes}")
    return "\n".join(lines)