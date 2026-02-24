"""
OGC API Client — Pure HTTP client for OGC API-compliant servers.

This module has ZERO MCP dependencies. It is a clean, reusable HTTP
client that works against any server conforming to OGC API standards
including pygeoapi, GeoServer, ldproxy, and any other implementation.

Supported OGC APIs:
    - OGC API - Common     (landing page, conformance, OpenAPI spec)
    - OGC API - Features   (collections, items, single feature)
    - OGC API - Records    (catalog search)
    - OGC API - Processes  (discovery, execution, job management)
    - OGC API - EDR        (environmental data retrieval)

License: Apache Software License, Version 2.0
"""

import asyncio
import httpx
from typing import Optional
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# Typed containers for OGC API responses.
# These decouple the rest of the system from raw JSON dicts.
# ═══════════════════════════════════════════════════════════════

@dataclass
class OGCServerInfo:
    """Summary information about an OGC API server."""
    title: str
    description: str
    base_url: str
    capabilities: list[str] = field(default_factory=list)
    conformance_classes: list[str] = field(default_factory=list)


@dataclass
class OGCCollection:
    """Represents a single OGC API collection (dataset)."""
    id: str
    title: str
    description: str
    links: list[dict] = field(default_factory=list)
    extent: Optional[dict] = None
    item_type: Optional[str] = "feature"
    crs: list[str] = field(default_factory=list)


@dataclass
class OGCProcess:
    """
    Represents a single OGC API process with full input/output schemas.
    The inputs and outputs are the raw OGC process schema dicts —
    mapper.py translates these into MCP Tool input schemas.
    """
    id: str
    title: str
    description: str
    version: str
    inputs: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    job_control_options: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass
class OGCJob:
    """Represents a running or completed OGC API processing job."""
    job_id: str
    status: str          # accepted | running | successful | failed | dismissed
    process_id: Optional[str] = None
    message: Optional[str] = None
    progress: Optional[int] = None
    created: Optional[str] = None
    finished: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# CUSTOM EXCEPTIONS
# Specific exception types allow callers to handle
# different failure modes appropriately.
# ═══════════════════════════════════════════════════════════════

class OGCClientError(Exception):
    """Base exception for all OGC client errors."""
    pass


class OGCServerNotFound(OGCClientError):
    """Server is unreachable — wrong URL or network issue."""
    pass


class OGCResourceNotFound(OGCClientError):
    """Requested resource (collection, process, job) does not exist."""
    pass


class OGCCollectionNotFound(OGCResourceNotFound):
    """Requested collection does not exist on this server."""
    pass


class OGCProcessNotFound(OGCResourceNotFound):
    """Requested process does not exist on this server."""
    pass


class OGCJobNotFound(OGCResourceNotFound):
    """Requested job ID does not exist."""
    pass


class OGCExecutionError(OGCClientError):
    """Process execution failed."""
    pass


class OGCTimeoutError(OGCClientError):
    """Request or job polling timed out."""
    pass


# ═══════════════════════════════════════════════════════════════
# MAIN CLIENT CLASS
# ═══════════════════════════════════════════════════════════════

class OGCClient:
    """
    Async HTTP client for OGC API-compliant geospatial servers.

    Designed to work against ANY conforming OGC API server — the
    implementation is fully generic and server-agnostic. Switch
    from demo.pygeoapi.io to a production GeoServer instance by
    changing only the base_url. No other code changes required.

    All methods are async and must be called with await.

    Usage:
        # As async context manager (recommended):
        async with OGCClient("https://demo.pygeoapi.io/master") as client:
            collections = await client.get_collections()
            features = await client.get_features("lakes", limit=5)

        # Manual lifecycle:
        client = OGCClient("https://demo.pygeoapi.io/master")
        collections = await client.get_collections()
        await client.close()
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        """
        Args:
            base_url: Root URL of any OGC API-compliant server.
                      Trailing slash is handled automatically.
                      Examples:
                        "https://demo.pygeoapi.io/master"
                        "http://localhost:5000"
                        "https://your-geoserver.org/ogc"
            timeout:  HTTP request timeout in seconds. Default 30s.
                      Increase for slow servers or large responses.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={
                "Accept": "application/json",
                "User-Agent": "ogc-mcp-server/0.1.0 (GSoC 2026)"
            },
            follow_redirects=True
        )

    async def close(self):
        """Release the underlying HTTP connection pool."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # ───────────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ───────────────────────────────────────────────────────────

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """
        Execute a GET request against the OGC server.

        Handles all HTTP-level error mapping to domain-specific
        exceptions so callers never deal with raw httpx errors.
        """
        url = f"{self.base_url}{path}"
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            return response.json()

        except httpx.ConnectError as e:
            raise OGCServerNotFound(
                f"Cannot connect to OGC server at '{self.base_url}'. "
                f"Verify the URL is correct and the server is running. "
                f"Original error: {e}"
            )
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 404:
                raise OGCResourceNotFound(
                    f"Resource not found at {url}"
                )
            raise OGCClientError(
                f"Server returned HTTP {status} for {url}. "
                f"Response: {e.response.text[:300]}"
            )
        except httpx.TimeoutException:
            raise OGCTimeoutError(
                f"Request to {url} timed out after {self.timeout}s. "
                f"Try increasing the timeout or check server performance."
            )
        except Exception as e:
            raise OGCClientError(
                f"Unexpected error calling {url}: {type(e).__name__}: {e}"
            )

    async def _post(self, path: str, payload: dict,
                    extra_headers: Optional[dict] = None) -> dict:
        """Execute a POST request against the OGC server."""
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        try:
            response = await self._client.post(
                url, json=payload, headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 404:
                raise OGCResourceNotFound(f"Resource not found at {url}")
            if status == 400:
                raise OGCExecutionError(
                    f"Bad request to {url}. "
                    f"Check input parameters. "
                    f"Server said: {e.response.text[:300]}"
                )
            raise OGCClientError(
                f"POST to {url} failed with HTTP {status}: "
                f"{e.response.text[:300]}"
            )
        except httpx.ConnectError as e:
            raise OGCServerNotFound(
                f"Cannot connect to OGC server at '{self.base_url}': {e}"
            )
        except httpx.TimeoutException:
            raise OGCTimeoutError(
                f"POST to {url} timed out after {self.timeout}s"
            )

    def _find_link_href(self, links: list[dict], rel: str) -> Optional[str]:
        """
        Find a link's href by relationship type.

        Handles both short rel names ("data", "items") and full
        OGC URI relationship identifiers like:
        "http://www.opengis.net/def/rel/ogc/1.0/processes"

        This is essential for server-agnostic link following —
        different OGC servers use different rel formats.
        """
        for link in links:
            link_rel = link.get("rel", "")
            # Exact match (e.g. "data", "self", "conformance")
            if link_rel == rel:
                return link.get("href")
            # Suffix match for OGC URIs
            # e.g. ".../ogc/1.0/processes" ends with "/processes"
            if link_rel.endswith(f"/{rel}"):
                return link.get("href")
        return None

    def _detect_capabilities(self, links: list[dict]) -> list[str]:
        """
        Detect which OGC API capabilities a server supports
        by inspecting its landing page links.

        Returns list of capability names:
        "features", "records", "processes", "tiles", "maps", "edr"
        """
        capability_rels = {
            "features": ["data", "collections"],
            "processes": ["processes", "http://www.opengis.net/def/rel/ogc/1.0/processes"],
            "tiles": ["tiling-schemes", "http://www.opengis.net/def/rel/ogc/1.0/tiling-schemes"],
            "jobs": ["job-list", "http://www.opengis.net/def/rel/ogc/1.0/job-list"],
        }
        all_rels = {link.get("rel", "") for link in links}
        capabilities = []
        for cap, rels in capability_rels.items():
            if any(rel in all_rels or
                   any(r.endswith(f"/{rel}") for r in all_rels)
                   for rel in rels):
                capabilities.append(cap)
        return capabilities

    # ───────────────────────────────────────────────────────────
    # OGC API - COMMON
    # ───────────────────────────────────────────────────────────

    async def get_server_info(self) -> OGCServerInfo:
        """
        Fetch and summarize key information about this OGC server.

        This is the recommended first call — it tells you the server's
        title, description, and what capabilities it supports, all
        in one structured object.

        Returns:
            OGCServerInfo with title, description, base_url, capabilities
        """
        page = await self._get("/")
        links = page.get("links", [])
        capabilities = self._detect_capabilities(links)

        conformance = []
        try:
            conf_data = await self._get("/conformance")
            conformance = conf_data.get("conformsTo", [])
        except OGCClientError:
            pass  # Conformance endpoint is optional

        return OGCServerInfo(
            title=page.get("title", "Unknown OGC Server"),
            description=page.get("description", ""),
            base_url=self.base_url,
            capabilities=capabilities,
            conformance_classes=conformance
        )

    async def get_landing_page(self) -> dict:
        """
        Fetch the raw OGC API landing page.

        Returns the complete landing page dict including all
        navigation links. Use get_server_info() for a cleaner
        summary, or this method when you need the raw links.
        """
        return await self._get("/")

    async def get_openapi_spec(self) -> dict:
        """
        Fetch the server's full OpenAPI 3.0 specification.

        The OpenAPI spec is the most complete machine-readable
        description of everything the server can do — all endpoints,
        all parameters, all response schemas. Used by mapper.py to
        auto-generate MCP Tool schemas dynamically.

        Returns:
            OpenAPI 3.0 specification dict
        """
        return await self._get("/openapi")

    # ───────────────────────────────────────────────────────────
    # OGC API - FEATURES & RECORDS
    # ───────────────────────────────────────────────────────────

    async def get_collections(self) -> list[OGCCollection]:
        """
        Discover ALL available collections (datasets) on this server.

        Collections represent individual datasets — geographic features
        like lakes, roads, buildings, or thematic records like metadata
        catalogs, sensor observations, or environmental measurements.

        Call this first to discover what data is available before
        fetching specific features.

        Returns:
            List of OGCCollection objects. Empty list if none found.
        """
        data = await self._get("/collections")
        result = []
        for col in data.get("collections", []):
            result.append(OGCCollection(
                id=col.get("id", ""),
                title=col.get("title", col.get("id", "Untitled")),
                description=col.get("description", "No description available."),
                links=col.get("links", []),
                extent=col.get("extent"),
                item_type=col.get("itemType", "feature"),
                crs=col.get("crs", ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"])
            ))
        return result

    async def get_collection(self, collection_id: str) -> OGCCollection:
        """
        Get full metadata for a specific collection.

        Args:
            collection_id: The collection identifier, e.g. "lakes"
                           Use get_collections() to find valid IDs.

        Returns:
            OGCCollection with complete metadata including spatial extent.

        Raises:
            OGCCollectionNotFound: If collection_id does not exist.
        """
        try:
            data = await self._get(f"/collections/{collection_id}")
        except OGCResourceNotFound:
            raise OGCCollectionNotFound(
                f"Collection '{collection_id}' does not exist on this server. "
                f"Call get_collections() to see available collection IDs."
            )
        return OGCCollection(
            id=data.get("id", collection_id),
            title=data.get("title", collection_id),
            description=data.get("description", ""),
            links=data.get("links", []),
            extent=data.get("extent"),
            item_type=data.get("itemType", "feature"),
            crs=data.get("crs", [])
        )

    async def get_features(
        self,
        collection_id: str,
        limit: int = 10,
        bbox: Optional[str] = None,
        datetime: Optional[str] = None,
        filter_cql: Optional[str] = None,
        properties: Optional[list[str]] = None,
        offset: int = 0
    ) -> dict:
        """
        Fetch geographic features from a collection as GeoJSON.

        Args:
            collection_id: Collection to query. Use get_collections()
                           to find valid IDs.
            limit:         Max features to return. Default 10, max
                           depends on server configuration.
            bbox:          Spatial bounding box filter.
                           Format: "minLon,minLat,maxLon,maxLat"
                           Example: "-10,35,40,75" filters to Europe.
                           Uses WGS84 (EPSG:4326) by default.
            datetime:      Temporal filter in ISO 8601.
                           Single instant: "2024-06-01T00:00:00Z"
                           Interval:       "2024-01-01/2024-12-31"
                           Open interval:  "../2024-12-31"
            filter_cql:    CQL2 attribute filter expression.
                           Example: "population > 1000000"
                           Example: "name LIKE 'Lake%'"
            properties:    Subset of properties to include.
                           Reduces response size for large features.
            offset:        Number of features to skip. Use with limit
                           for pagination through large datasets.

        Returns:
            GeoJSON FeatureCollection dict with "type", "features",
            "numberMatched", "numberReturned", and navigation links.
        """
        params: dict = {"limit": limit, "f": "json"}
        if offset > 0:
            params["offset"] = offset
        if bbox:
            params["bbox"] = bbox
        if datetime:
            params["datetime"] = datetime
        if filter_cql:
            params["filter"] = filter_cql
            params["filter-lang"] = "cql2-text"
        if properties:
            params["properties"] = ",".join(properties)

        return await self._get(
            f"/collections/{collection_id}/items",
            params=params
        )

    async def get_feature(
        self,
        collection_id: str,
        feature_id: str
    ) -> dict:
        """
        Fetch a single geographic feature by its unique ID.

        Args:
            collection_id: The collection containing the feature.
            feature_id:    The feature's unique identifier.

        Returns:
            GeoJSON Feature dict with geometry and properties.
        """
        return await self._get(
            f"/collections/{collection_id}/items/{feature_id}"
        )

    # ───────────────────────────────────────────────────────────
    # OGC API - PROCESSES
    # ───────────────────────────────────────────────────────────

    async def get_processes(self) -> list[OGCProcess]:
        """
        Discover ALL available geospatial processes on this server.

        Processes represent executable geospatial analyses — things
        like buffer operations, spatial intersections, cool spot
        analysis, zonal statistics, or any custom algorithm the
        server operator has deployed.

        Returns:
            List of OGCProcess objects. Each has id, title, description,
            and input/output schemas defining what the process needs
            and what it produces.
        """
        data = await self._get("/processes")
        result = []
        for proc in data.get("processes", []):
            result.append(OGCProcess(
                id=proc.get("id", ""),
                title=proc.get("title", proc.get("id", "Untitled")),
                description=proc.get("description", "No description available."),
                version=proc.get("version", "1.0.0"),
                inputs=proc.get("inputs", {}),
                outputs=proc.get("outputs", {}),
                job_control_options=proc.get(
                    "jobControlOptions", ["sync-execute"]
                ),
                keywords=proc.get("keywords", [])
            ))
        return result

    async def get_process(self, process_id: str) -> OGCProcess:
        """
        Get full details for a specific process including complete
        input and output schemas.

        The input schema tells you exactly what parameters the process
        requires, their types, and any constraints. This is used by
        mapper.py to generate the corresponding MCP Tool input schema.

        Args:
            process_id: The process identifier, e.g. "hello-world"
                        Use get_processes() to find valid IDs.

        Returns:
            OGCProcess with complete inputs/outputs schema.

        Raises:
            OGCProcessNotFound: If process_id does not exist.
        """
        try:
            data = await self._get(f"/processes/{process_id}")
        except OGCResourceNotFound:
            raise OGCProcessNotFound(
                f"Process '{process_id}' does not exist on this server. "
                f"Call get_processes() to see available process IDs."
            )
        return OGCProcess(
            id=data.get("id", process_id),
            title=data.get("title", process_id),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            job_control_options=data.get(
                "jobControlOptions", ["sync-execute"]
            ),
            keywords=data.get("keywords", [])
        )

    async def execute_process(
        self,
        process_id: str,
        inputs: dict,
        async_execute: bool = False
    ) -> dict:
        """
        Execute a geospatial process on the OGC server.

        Supports both synchronous and asynchronous execution modes.
        Use async_execute=True for long-running processes — the server
        immediately returns a job ID and you poll for completion using
        poll_job_until_complete().

        Args:
            process_id:    The process to execute.
            inputs:        Input values as a dict matching the process
                           input schema from get_process().
            async_execute: False (default) = wait for result synchronously.
                           True = return job ID immediately, poll later.

        Returns:
            Sync:  The direct output dict from the process.
            Async: A job status dict with "jobID" and "status".

        Raises:
            OGCProcessNotFound: If process_id does not exist.
            OGCExecutionError:  If the process fails validation or execution.
        """
        extra_headers = {}
        if async_execute:
            extra_headers["Prefer"] = "respond-async"

        try:
            return await self._post(
                f"/processes/{process_id}/execution",
                payload={"inputs": inputs},
                extra_headers=extra_headers
            )
        except OGCResourceNotFound:
            raise OGCProcessNotFound(
                f"Process '{process_id}' not found. "
                f"Use get_processes() to see available processes."
            )

    async def get_job_status(self, job_id: str) -> OGCJob:
        """
        Check the current status of an async processing job.

        Status values follow the OGC API - Processes standard:
            "accepted"   — job queued, not yet started
            "running"    — actively executing
            "successful" — completed, results available
            "failed"     — execution failed, check message
            "dismissed"  — job was cancelled

        Args:
            job_id: The job identifier from async execute_process().

        Returns:
            OGCJob with current status and optional progress/message.
        """
        try:
            data = await self._get(f"/jobs/{job_id}")
        except OGCResourceNotFound:
            raise OGCJobNotFound(
                f"Job '{job_id}' not found. "
                f"It may have expired or never existed."
            )
        return OGCJob(
            job_id=data.get("jobID", job_id),
            status=data.get("status", "unknown"),
            process_id=data.get("processID"),
            message=data.get("message"),
            progress=data.get("progress"),
            created=data.get("created"),
            finished=data.get("finished")
        )

    async def get_job_results(self, job_id: str) -> dict:
        """
        Retrieve the output of a successfully completed job.

        Only call this after get_job_status() returns status="successful".
        Calling before completion will return an error from the server.

        Args:
            job_id: The job identifier from async execute_process().

        Returns:
            The process output dict — structure matches the process's
            output schema from get_process().
        """
        return await self._get(f"/jobs/{job_id}/results")

    async def poll_job_until_complete(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        max_wait: float = 300.0
    ) -> OGCJob:
        """
        Poll a job's status repeatedly until it succeeds or fails.

        Designed for use after async execute_process(). Handles the
        full job lifecycle: accepted → running → successful/failed.

        Args:
            job_id:        Job identifier to monitor.
            poll_interval: Seconds between status checks. Default 2s.
                           Reduce for fast processes, increase for
                           long-running analyses.
            max_wait:      Maximum total seconds to wait. Default 5 min.
                           Raises OGCTimeoutError if exceeded.

        Returns:
            OGCJob with status="successful".

        Raises:
            OGCExecutionError: If job fails or is dismissed.
            OGCTimeoutError:   If job does not complete within max_wait.
        """
        elapsed = 0.0
        while elapsed < max_wait:
            job = await self.get_job_status(job_id)

            if job.status == "successful":
                return job

            if job.status == "failed":
                raise OGCExecutionError(
                    f"Job '{job_id}' failed. "
                    f"Server message: {job.message or 'No details provided.'}"
                )

            if job.status == "dismissed":
                raise OGCExecutionError(
                    f"Job '{job_id}' was dismissed before completion."
                )

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise OGCTimeoutError(
            f"Job '{job_id}' did not complete within {max_wait}s. "
            f"Last status: {job.status}. "
            f"Consider increasing max_wait for long-running processes."
        )
    