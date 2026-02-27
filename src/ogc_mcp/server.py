"""
OGC MCP Server — MCP protocol server for OGC API geospatial services.

Architecture:
    server.py     ← YOU ARE HERE (MCP protocol layer)
        ↓
    mapper.py     ← Translates OGC objects to MCP objects
        ↓
    ogc_client.py ← Pure HTTP client for OGC API servers

Supports:
- OGC API - Common (discovery, collections)
- OGC API - Features (spatial data queries)
- OGC API - Records (catalog metadata search)              ← NEW Stage 5
- OGC API - EDR (environmental data position/area queries) ← NEW Stage 5
- OGC API - Processes (process execution, job management)

License: Apache Software License, Version 2.0
"""

import asyncio
import json
import logging
import os
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# Import handling — supports both package and direct run
# ─────────────────────────────────────────────

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
        build_discovery_tools,
        build_workflow_prompts,
        format_server_info,
        format_collections,
        format_processes,
        format_features,
        format_process_detail,
        collection_to_resource,
        process_to_tool,
        # NEW Stage 5: Records
        format_catalog_records,
        format_catalog_record_detail,
        # NEW Stage 5: EDR
        format_edr_query_result,
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
        build_discovery_tools,
        build_workflow_prompts,
        format_server_info,
        format_collections,
        format_processes,
        format_features,
        format_process_detail,
        collection_to_resource,
        process_to_tool,
        # NEW Stage 5: Records
        format_catalog_records,
        format_catalog_record_detail,
        # NEW Stage 5: EDR
        format_edr_query_result,
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
# MCP Server Instance
# ─────────────────────────────────────────────

app = Server("ogc-mcp-server")


# ═══════════════════════════════════════════════════════════════
# TOOLS — Actions the LLM can take
# ═══════════════════════════════════════════════════════════════

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return all tools available on this MCP server."""
    return build_discovery_tools()


@app.call_tool()
async def call_tool(
    name: str,
    arguments: dict[str, Any]
) -> list[types.TextContent]:
    """
    Execute a tool by name with the provided arguments.

    Central dispatcher — all tool calls from LLMs arrive here
    and are routed to the appropriate OGC API operation.
    """
    logger.info(f"Tool called: {name} with args: {list(arguments.keys())}")

    try:
        result = await _dispatch_tool(name, arguments)
        return [types.TextContent(type="text", text=result)]

    except OGCServerNotFound as e:
        return [types.TextContent(type="text", text=f"Error: Cannot reach OGC server: {e}")]

    except OGCCollectionNotFound as e:
        return [types.TextContent(type="text", text=f"Collection not found: {e}")]

    except OGCProcessNotFound as e:
        return [types.TextContent(type="text", text=f"Process not found: {e}")]

    except OGCExecutionError as e:
        return [types.TextContent(type="text", text=f"Execution failed: {e}")]

    except OGCClientError as e:
        return [types.TextContent(type="text", text=f"OGC API error: {e}")]

    except Exception as e:
        logger.exception(f"Unexpected error in tool {name}")
        return [types.TextContent(
            type="text",
            text=f"Unexpected server error: {type(e).__name__}: {e}"
        )]


async def _dispatch_tool(name: str, args: dict) -> str:
    """Route tool calls to the correct OGC API operations."""
    server_url = args.get("server_url", DEFAULT_SERVER_URL)

    async with OGCClient(server_url) as client:

        # ── Discovery ───────────────────────────────────────

        if name == "discover_ogc_server":
            info = await client.get_server_info()
            return format_server_info(info)

        elif name == "get_collections":
            collections = await client.get_collections()
            return format_collections(collections)

        elif name == "get_collection_detail":
            collection_id = args["collection_id"]
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

        # ── Features ────────────────────────────────────────

        elif name == "get_features":
            collection_id = args["collection_id"]
            geojson = await client.get_features(
                collection_id=collection_id,
                limit=args.get("limit", 10),
                bbox=args.get("bbox"),
                datetime=args.get("datetime"),
                filter_cql=args.get("filter_cql"),
            )
            return format_features(geojson)

        # ── Processes ───────────────────────────────────────

        elif name == "discover_processes":
            processes = await client.get_processes()
            return format_processes(processes)

        elif name == "get_process_detail":
            process_id = args["process_id"]
            process = await client.get_process(process_id)
            return format_process_detail(process)

        elif name == "execute_process":
            process_id = args["process_id"]
            inputs = args["inputs"]
            async_execute = args.get("async_execute", False)
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
                    f"Use get_job_status with job_id='{job_id}' to monitor."
                )
            return json.dumps(result, indent=2, default=str)

        elif name == "get_job_status":
            job_id = args["job_id"]
            job = await client.get_job_status(job_id)
            return (
                f"Job: {job.job_id}\n"
                f"Status: {job.status}\n"
                f"Progress: {job.progress}%\n"
                f"Message: {job.message}"
            )

        elif name == "get_job_results":
            job_id = args["job_id"]
            result = await client.get_job_results(job_id)
            return json.dumps(result, indent=2, default=str)

        # ══ NEW Stage 5: Records ════════════════════════════

        elif name == "search_catalog":
            catalog_id = args["catalog_id"]
            geojson = await client.search_records(
                collection_id=catalog_id,
                q=args.get("q"),
                bbox=args.get("bbox"),
                datetime=args.get("datetime"),
                limit=args.get("limit", 10),
            )
            return format_catalog_records(geojson)

        elif name == "get_catalog_record":
            catalog_id = args["catalog_id"]
            record_id = args["record_id"]
            record = await client.get_record(catalog_id, record_id)
            return format_catalog_record_detail(record)

        # ══ NEW Stage 5: EDR ════════════════════════════════

        elif name == "query_edr_position":
            collection_id = args["collection_id"]
            coords = args["coords"]
            result = await client.query_edr_position(
                collection_id=collection_id,
                coords=coords,
                parameter_name=args.get("parameter_name"),
                datetime=args.get("datetime"),
            )
            return format_edr_query_result(result, "position")

        elif name == "query_edr_area":
            collection_id = args["collection_id"]
            coords = args["coords"]
            result = await client.query_edr_area(
                collection_id=collection_id,
                coords=coords,
                parameter_name=args.get("parameter_name"),
                datetime=args.get("datetime"),
            )
            return format_edr_query_result(result, "area")

        # ── Unknown ─────────────────────────────────────────

        else:
            raise ValueError(f"Unknown tool: {name}")


# ═══════════════════════════════════════════════════════════════
# RESOURCES — Data the LLM reads for context
# ═══════════════════════════════════════════════════════════════

@app.list_resources()
async def list_resources() -> list[types.Resource]:
    """List all available MCP Resources (collection metadata)."""
    resources = []
    try:
        async with OGCClient(DEFAULT_SERVER_URL) as client:
            collections = await client.get_collections()
            for col in collections:
                resources.append(collection_to_resource(col, DEFAULT_SERVER_URL))
    except Exception as e:
        logger.warning(f"Could not fetch resources: {e}")
    return resources


@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read a specific Resource's content by URI."""
    # Parse collection ID from URI: ogc://server/collections/{id}
    parts = str(uri).split("/collections/")
    if len(parts) == 2:
        collection_id = parts[1]
        try:
            async with OGCClient(DEFAULT_SERVER_URL) as client:
                collection = await client.get_collection(collection_id)
                lines = [
                    f"Collection: {collection.title}",
                    f"ID: {collection.id}",
                    f"Description: {collection.description}",
                    f"Item type: {collection.item_type}",
                ]
                if collection.extent:
                    lines.append(f"Extent: {json.dumps(collection.extent)}")
                return "\n".join(lines)
        except Exception as e:
            return f"Error reading resource: {e}"
    return f"Unknown resource URI: {uri}"


# ═══════════════════════════════════════════════════════════════
# PROMPTS — Workflow templates for the LLM
# ═══════════════════════════════════════════════════════════════

@app.list_prompts()
async def list_prompts() -> list[types.Prompt]:
    return build_workflow_prompts()


@app.get_prompt()
async def get_prompt(name: str, arguments: dict) -> types.GetPromptResult:
    server_url = arguments.get("server_url", DEFAULT_SERVER_URL)
    goal = arguments.get("analysis_goal", "perform geospatial analysis")

    if name == "spatial_analysis_workflow":
        text = (
            f"Spatial Analysis Workflow for: {goal}\n\n"
            f"Step 1: Discover the server at {server_url} using discover_ogc_server\n"
            f"Step 2: List collections using get_collections\n"
            f"Step 3: Identify the relevant collection for your goal\n"
            f"Step 4: Get collection details using get_collection_detail\n"
            f"Step 5: Query features using get_features with appropriate filters\n"
            f"Step 6: Analyze and present the results"
        )
    elif name == "process_execution_workflow":
        text = (
            f"Process Execution Workflow for: {goal}\n\n"
            f"Step 1: Discover available processes using discover_processes\n"
            f"Step 2: Find the process matching your analysis goal\n"
            f"Step 3: Get process details using get_process_detail\n"
            f"Step 4: Prepare inputs matching the process schema\n"
            f"Step 5: Execute using execute_process\n"
            f"Step 6: If async, monitor with get_job_status until complete\n"
            f"Step 7: Retrieve results with get_job_results\n"
            f"Step 8: Present results to the user"
        )
    elif name == "data_discovery_workflow":
        text = (
            f"Data Discovery Workflow for: {goal}\n\n"
            f"Step 1: List collections using get_collections\n"
            f"Step 2: Identify catalog collections (itemType='record')\n"
            f"Step 3: Search the catalog using search_catalog with keywords from your goal\n"
            f"Step 4: Review matching records for relevance\n"
            f"Step 5: Get full details using get_catalog_record\n"
            f"Step 6: Access the referenced data via provided links"
        )
    else:
        text = f"Unknown prompt: {name}"

    return types.GetPromptResult(
        description=f"Workflow for: {goal}",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(type="text", text=text)
            )
        ]
    )


# ═══════════════════════════════════════════════════════════════
# SERVER STARTUP
# ═══════════════════════════════════════════════════════════════

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
