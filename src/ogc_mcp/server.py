"""
OGC MCP Server — FastMCP server exposing OGC API capabilities to LLMs.

Uses FastMCP (the official recommended MCP server framework) for clean,
decorator-based tool, resource, and prompt registration while keeping
all OGC API logic cleanly separated in ogc_client.py and mapper.py.

Architecture:
    server.py     ← YOU ARE HERE (MCP protocol layer, FastMCP)
        ↓
    mapper.py     ← Translates OGC objects to MCP objects
        ↓
    ogc_client.py ← Pure HTTP client for OGC API servers

License: Apache Software License, Version 2.0
"""

import json
import logging
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

try:
    from .ogc_client import (
        OGCClient,
        OGCClientError,
        OGCCollectionNotFound,
        OGCProcessNotFound,
        OGCServerNotFound,
        OGCExecutionError,
    )
    from .mapper import (
        format_server_info,
        format_collections,
        format_processes,
        format_features,
        format_process_detail,
        collection_to_resource,
    )
except ImportError:
    from ogc_mcp.ogc_client import (
        OGCClient,
        OGCClientError,
        OGCCollectionNotFound,
        OGCProcessNotFound,
        OGCServerNotFound,
        OGCExecutionError,
    )
    from ogc_mcp.mapper import (
        format_server_info,
        format_collections,
        format_processes,
        format_features,
        format_process_detail,
        collection_to_resource,
    )

# ─────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ogc-mcp-server")

DEFAULT_SERVER_URL = os.getenv(
    "OGC_SERVER_URL",
    "https://demo.pygeoapi.io/master"
)

# ─────────────────────────────────────────────
# FastMCP Server Instance
# ─────────────────────────────────────────────

mcp = FastMCP(
    name="OGC MCP Server",
    instructions=(
        "You are a geospatial assistant connected to OGC API-compliant servers. "
        "You can discover available datasets and processes, fetch geographic features, "
        "and execute spatial analyses on any OGC-compliant server. "
        "Always start by using discover_ogc_server to understand what a server offers, "
        "then use get_collections for data or discover_processes for analyses. "
        "For any spatial analysis, use get_process_detail before execute_process "
        "to understand required inputs."
    )
)


# ═══════════════════════════════════════════════════════════════
# TOOLS — Actions the LLM can take
# Each @mcp.tool() decorator registers a function as an MCP Tool.
# The function's docstring becomes the tool description the LLM reads.
# Type hints become the inputSchema the LLM uses to call the tool.
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def discover_ogc_server(server_url: str) -> str:
    """
    Discover the capabilities of any OGC API-compliant geospatial server.
    Returns the server title, description, and supported capabilities
    such as features, processes, tiles, and jobs.
    Use this as the FIRST call when connecting to a new OGC server
    to understand what it offers before making more specific requests.
    Example server URLs: https://demo.pygeoapi.io/master
    """
    async with OGCClient(server_url) as client:
        info = await client.get_server_info()
        return format_server_info(info)


@mcp.tool()
async def get_collections(server_url: str) -> str:
    """
    List all available geospatial datasets (collections) on an OGC API server.
    Returns each collection's ID, title, and description.
    Use the returned collection IDs with get_features() to fetch actual geodata.
    Call this to answer questions like 'what data is available on this server?'
    or 'does this server have flood risk or land use data?'
    """
    async with OGCClient(server_url) as client:
        collections = await client.get_collections()
        return format_collections(collections)


@mcp.tool()
async def get_collection_detail(server_url: str, collection_id: str) -> str:
    """
    Get detailed metadata for a specific geospatial collection including
    its spatial extent, coordinate reference system, and item type.
    Use before get_features() to understand the collection's geographic
    coverage and confirm it contains data for your area of interest.
    Get valid collection IDs from get_collections() first.
    """
    async with OGCClient(server_url) as client:
        collection = await client.get_collection(collection_id)
        lines = [
            f"Collection: {collection.title} (ID: {collection.id})",
            f"Description: {collection.description}",
            f"Item type: {collection.item_type}",
        ]
        if collection.extent:
            spatial = collection.extent.get("spatial", {})
            bbox = spatial.get("bbox", [])
            if bbox:
                b = bbox[0]
                lines.append(f"Spatial extent: {b}")
        return "\n".join(lines)


@mcp.tool()
async def get_features(
    server_url: str,
    collection_id: str,
    limit: int = 10,
    bbox: Optional[str] = None,
    datetime: Optional[str] = None,
    filter_cql: Optional[str] = None
) -> str:
    """
    Fetch geographic features from a collection as GeoJSON.
    Supports spatial filtering by bounding box (bbox), temporal filtering
    by date or time range (datetime), and attribute filtering via CQL2.
    Returns feature names, geometry types, and key properties.

    bbox format:     'minLon,minLat,maxLon,maxLat'
                     Example: '-10,35,40,75' for Europe
                     Example: '6.5,51.0,8.0,52.5' for NRW Germany

    datetime format: Single instant: '2024-06-01T00:00:00Z'
                     Interval:       '2024-01-01/2024-12-31'

    filter_cql:      CQL2 expression like "population > 1000000"
    """
    async with OGCClient(server_url) as client:
        geojson = await client.get_features(
            collection_id=collection_id,
            limit=limit,
            bbox=bbox,
            datetime=datetime,
            filter_cql=filter_cql
        )
        return format_features(geojson)


@mcp.tool()
async def discover_processes(server_url: str) -> str:
    """
    List all geospatial analysis processes available on an OGC API server.
    Returns each process ID, title, and description.
    Processes represent executable spatial analyses such as buffer operations,
    cool spot analysis, zonal statistics, intersection, or any custom
    algorithm the server operator has deployed.
    Use process IDs with get_process_detail() and execute_process().
    """
    async with OGCClient(server_url) as client:
        processes = await client.get_processes()
        return format_processes(processes)


@mcp.tool()
async def get_process_detail(server_url: str, process_id: str) -> str:
    """
    Get full details for a specific geospatial process including its
    complete input parameter schema and expected output format.
    ALWAYS call this before execute_process() to understand exactly
    what inputs are required, their types, and correct format.
    This allows pre-filling known parameters and asking the user
    only for genuinely missing inputs.
    Get valid process IDs from discover_processes() first.
    """
    async with OGCClient(server_url) as client:
        process = await client.get_process(process_id)
        return format_process_detail(process)


@mcp.tool()
async def execute_process(
    server_url: str,
    process_id: str,
    inputs: dict,
    async_execute: bool = False
) -> str:
    """
    Execute any geospatial process on an OGC API server.
    Supports synchronous execution (waits for result, good for fast processes)
    and asynchronous execution (returns job ID immediately, good for
    long-running spatial analyses like cool spot analysis or zonal statistics).
    Always call get_process_detail() first to understand required inputs.
    For async jobs, use get_job_status() to monitor and get_job_results()
    to retrieve output once complete.

    inputs: JSON object with keys matching the process input schema.
            Example: {"name": "test", "message": "hello"}
    async_execute: Set true for long-running processes. Default false.
    """
    async with OGCClient(server_url) as client:
        result = await client.execute_process(
            process_id=process_id,
            inputs=inputs,
            async_execute=async_execute
        )
        if async_execute:
            job_id = result.get("jobID", "unknown")
            status = result.get("status", "accepted")
            return (
                f"Process '{process_id}' submitted asynchronously.\n"
                f"Job ID: {job_id}\n"
                f"Status: {status}\n"
                f"Use get_job_status with job_id='{job_id}' to monitor progress."
            )
        else:
            return (
                f"Process '{process_id}' completed successfully.\n"
                f"Result:\n{json.dumps(result, indent=2)}"
            )


@mcp.tool()
async def get_job_status(server_url: str, job_id: str) -> str:
    """
    Check the status of an asynchronous geospatial processing job.
    Returns status: accepted, running, successful, failed, or dismissed.
    Poll this after async execute_process() until status is 'successful',
    then call get_job_results() to retrieve the output data.
    """
    async with OGCClient(server_url) as client:
        job = await client.get_job_status(job_id)
        lines = [
            f"Job ID: {job.job_id}",
            f"Status: {job.status}",
        ]
        if job.process_id:
            lines.append(f"Process: {job.process_id}")
        if job.progress is not None:
            lines.append(f"Progress: {job.progress}%")
        if job.message:
            lines.append(f"Message: {job.message}")
        if job.status == "successful":
            lines.append(
                f"Job complete. Call get_job_results with "
                f"job_id='{job.job_id}' to retrieve the output."
            )
        return "\n".join(lines)


@mcp.tool()
async def get_job_results(server_url: str, job_id: str) -> str:
    """
    Retrieve the output of a successfully completed async processing job.
    Only call this after get_job_status() returns status='successful'.
    Returns the process output — typically GeoJSON, statistics,
    or other geospatial analysis results.
    """
    async with OGCClient(server_url) as client:
        results = await client.get_job_results(job_id)
        return (
            f"Results for job '{job_id}':\n"
            f"{json.dumps(results, indent=2)}"
        )


# ═══════════════════════════════════════════════════════════════
# RESOURCES — Data the LLM can read for context
# URI scheme: ogc://{server_identifier}/collections/{collection_id}
# ═══════════════════════════════════════════════════════════════

@mcp.resource("ogc://collections/list")
async def list_collections_resource() -> str:
    """
    All available collections on the default OGC server as a resource.
    The LLM reads this for context about what datasets are available
    before deciding which tools to call.
    """
    async with OGCClient(DEFAULT_SERVER_URL) as client:
        collections = await client.get_collections()
        return format_collections(collections)


@mcp.resource("ogc://processes/list")
async def list_processes_resource() -> str:
    """
    All available processes on the default OGC server as a resource.
    The LLM reads this for context about what analyses can be run.
    """
    async with OGCClient(DEFAULT_SERVER_URL) as client:
        processes = await client.get_processes()
        return format_processes(processes)


@mcp.resource("ogc://server/info")
async def server_info_resource() -> str:
    """
    Summary information about the default OGC server including
    its title, description, and supported capabilities.
    """
    async with OGCClient(DEFAULT_SERVER_URL) as client:
        info = await client.get_server_info()
        return format_server_info(info)


# ═══════════════════════════════════════════════════════════════
# PROMPTS — Generic workflow templates for multi-step operations
# These are NOT hardcoded to cool spots — they work for ANY
# OGC API operation. Cool spot analysis is just one instance
# of the spatial_analysis_workflow prompt.
# ═══════════════════════════════════════════════════════════════

@mcp.prompt()
def spatial_analysis_workflow(
    server_url: str,
    analysis_goal: str,
    user_data_description: str = ""
) -> str:
    """
    Guide through a complete spatial analysis workflow on any OGC server.
    Works for any process: cool spot analysis, buffer, intersection,
    zonal statistics, or any custom geospatial algorithm.
    Steps: discover server → find process → understand inputs →
    validate user data → execute → monitor → present results.
    """
    data_line = f"My available data: {user_data_description}\n" if user_data_description else ""
    return (
        f"I want to perform the following spatial analysis: {analysis_goal}\n"
        f"OGC API Server: {server_url}\n"
        f"{data_line}\n"
        "Please guide me through this by following these steps:\n"
        "1. Use discover_ogc_server to understand what this server offers.\n"
        "2. Use discover_processes to find processes relevant to my goal.\n"
        "3. Use get_process_detail on the most relevant process to understand its inputs.\n"
        "4. Tell me what inputs are needed and pre-fill any you can determine from context.\n"
        "5. Ask me only for inputs you cannot determine yourself.\n"
        "6. Use execute_process once all inputs are confirmed.\n"
        "7. If the job is async, use get_job_status to monitor progress.\n"
        "8. Use get_job_results and explain the output to me in plain language."
    )


@mcp.prompt()
def data_discovery_workflow(
    server_url: str,
    data_need: str,
    area_of_interest: str = ""
) -> str:
    """
    Guide through discovering and fetching relevant geospatial data.
    Works for any OGC API Features or Records server.
    Steps: explore collections → filter by topic/location/time →
    fetch matching features → summarize results in plain language.
    """
    area_line = f"Area of interest: {area_of_interest}\n" if area_of_interest else ""
    return (
        f"I need to find: {data_need}\n"
        f"OGC API Server: {server_url}\n"
        f"{area_line}\n"
        "Please follow these steps:\n"
        "1. Use get_collections to see all available datasets on this server.\n"
        "2. Identify which collections are most relevant to my data need.\n"
        "3. Use get_collection_detail for the most relevant collection.\n"
        "4. Use get_features with appropriate filters "
        f"{'and a bbox for ' + area_of_interest if area_of_interest else ''}.\n"
        "5. Summarize what you found in plain language including feature count, "
        "geographic coverage, and key properties."
    )


@mcp.prompt()
def server_exploration_workflow(server_url: str) -> str:
    """
    Guide through fully exploring an unknown OGC API server.
    Discovers all capabilities, datasets, and processes,
    then summarizes what the server offers in plain language.
    Good for first-time exploration of a new geospatial server.
    """
    return (
        f"Please fully explore the OGC API server at: {server_url}\n\n"
        "Follow these steps in order:\n"
        "1. Use discover_ogc_server to get the server overview and capabilities.\n"
        "2. Use get_collections to list every available dataset.\n"
        "3. Use discover_processes to list every available spatial analysis.\n"
        "4. Give me a comprehensive plain-language summary covering:\n"
        "   - What this server is and who operates it\n"
        "   - What datasets are available and their topics\n"
        "   - What analyses can be run\n"
        "   - What kinds of questions I could answer using this server"
    )


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def run():
    """Synchronous entry point for command-line use."""
    mcp.run()


if __name__ == "__main__":
    run()