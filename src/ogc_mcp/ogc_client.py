"""
OGC API Client — Pure HTTP client for OGC-compliant servers.

This module has NO MCP dependencies. It is a clean, reusable
client that works against any OGC API-compliant server.

Implements discovery and data access for:
- OGC API - Common (landing page, conformance)
- OGC API - Features (collections, items)
- OGC API - Records (catalog search, record retrieval)          ← NEW Stage 5
- OGC API - Environmental Data Retrieval (position, area)       ← NEW Stage 5
- OGC API - Processes (process discovery, execution, job management)

License: Apache Software License, Version 2.0
"""

import httpx
from typing import Optional
from dataclasses import dataclass, field


# ─────────────────────────────────────────────
# Custom exceptions
# ─────────────────────────────────────────────

class OGCClientError(Exception):
    """Base exception for all OGC client errors."""
    pass

class OGCServerNotFound(OGCClientError):
    """Raised when the OGC server is unreachable."""
    pass

class OGCCollectionNotFound(OGCClientError):
    """Raised when a requested collection does not exist."""
    pass

class OGCProcessNotFound(OGCClientError):
    """Raised when a requested process does not exist."""
    pass

class OGCExecutionError(OGCClientError):
    """Raised when process execution fails."""
    pass

class OGCTimeoutError(OGCClientError):
    """Raised when a job exceeds the maximum wait time."""
    pass


# ─────────────────────────────────────────────
# Data classes — typed containers for OGC data
# ─────────────────────────────────────────────

@dataclass
class OGCServerInfo:
    """Represents OGC API server landing page information."""
    title: str
    description: str
    capabilities: list[str]
    links: list[dict]

@dataclass
class OGCCollection:
    """Represents a single OGC API collection (dataset)."""
    id: str
    title: str
    description: str
    links: list[dict]
    extent: Optional[dict] = None
    item_type: Optional[str] = None

@dataclass
class OGCProcess:
    """Represents a single OGC API process."""
    id: str
    title: str
    description: str
    version: str = "1.0.0"
    inputs: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    job_control_options: list[str] = field(default_factory=lambda: ["sync-execute"])

@dataclass
class OGCJob:
    """Represents an OGC API job status."""
    job_id: str
    status: str
    type: str = ""
    progress: int = 0
    message: str = ""
    created: str = ""
    updated: str = ""

# ─── NEW Stage 5: Records dataclasses ────────

@dataclass
class OGCRecord:
    """Represents a single OGC API Records catalog entry."""
    id: str
    title: str
    description: str
    type: str                                    # e.g., "dataset", "service"
    keywords: list[str]
    links: list[dict]
    bbox: Optional[list] = None
    time: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None
    properties: Optional[dict] = None

# ─── NEW Stage 5: EDR dataclasses ────────────

@dataclass
class OGCEDRParameter:
    """Represents a parameter available in an EDR collection."""
    id: str
    label: str
    description: str
    unit: Optional[str] = None
    unit_label: Optional[str] = None

@dataclass
class OGCEDRCollection:
    """Represents an EDR collection with its query capabilities."""
    id: str
    title: str
    description: str
    parameters: list[OGCEDRParameter]
    query_types: list[str]
    extent: Optional[dict] = None
    crs: Optional[list[str]] = None
    output_formats: Optional[list[str]] = None


# ─────────────────────────────────────────────
# OGC API Client
# ─────────────────────────────────────────────

class OGCClient:
    """
    Async HTTP client for OGC API-compliant servers.

    Usage:
        async with OGCClient("https://demo.pygeoapi.io/master") as client:
            info = await client.get_server_info()
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """Make a GET request and return JSON."""
        if params is None:
            params = {}
        if "f" not in params:
            params["f"] = "json"

        url = f"{self.base_url}{path}"
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            # EDR endpoints may return CoverageJSON with non-standard
            # content-types. Try json() first, fall back to manual parse.
            try:
                return response.json()
            except Exception:
                import json as _json
                text = response.text
                if text and text.strip():
                    return _json.loads(text)
                return {}
        except httpx.ConnectError:
            raise OGCServerNotFound(f"Cannot connect to {self.base_url}")
        except httpx.TimeoutException:
            raise OGCServerNotFound(f"Timeout connecting to {self.base_url}")
        except httpx.HTTPStatusError as e:
            raise OGCClientError(f"HTTP {e.response.status_code} from {url}")

    async def _post(self, path: str, json_data: dict, headers: Optional[dict] = None) -> dict:
        """Make a POST request and return JSON."""
        url = f"{self.base_url}{path}"
        default_headers = {"Content-Type": "application/json"}
        if headers:
            default_headers.update(headers)

        try:
            response = await self._client.post(url, json=json_data, headers=default_headers)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            raise OGCServerNotFound(f"Cannot connect to {self.base_url}")
        except httpx.HTTPStatusError as e:
            raise OGCExecutionError(f"HTTP {e.response.status_code}: {e.response.text[:200]}")

    # ── OGC API - Common ──────────────────────────

    async def get_landing_page(self) -> dict:
        return await self._get("/")

    async def get_server_info(self) -> OGCServerInfo:
        data = await self.get_landing_page()
        capabilities = set()
        for link in data.get("links", []):
            rel = link.get("rel", "")
            href = link.get("href", "")
            if "processes" in href or rel == "http://www.opengis.net/def/rel/ogc/1.0/processes":
                capabilities.add("processes")
            if "collections" in href:
                capabilities.add("features")
            if "jobs" in href:
                capabilities.add("jobs")
            if "tiles" in href:
                capabilities.add("tiles")
        return OGCServerInfo(
            title=data.get("title", "Unknown"),
            description=data.get("description", ""),
            capabilities=sorted(capabilities),
            links=data.get("links", [])
        )

    async def get_conformance(self) -> list[str]:
        data = await self._get("/conformance")
        return data.get("conformsTo", [])

    # ── OGC API - Features ────────────────────────

    async def get_collections(self) -> list[OGCCollection]:
        data = await self._get("/collections")
        collections = []
        for col in data.get("collections", []):
            collections.append(OGCCollection(
                id=col.get("id", ""),
                title=col.get("title", col.get("id", "")),
                description=col.get("description", ""),
                links=col.get("links", []),
                extent=col.get("extent", None),
                item_type=col.get("itemType", None)
            ))
        return collections

    async def get_collection(self, collection_id: str) -> OGCCollection:
        try:
            data = await self._get(f"/collections/{collection_id}")
        except OGCClientError as e:
            if "404" in str(e):
                raise OGCCollectionNotFound(f"Collection '{collection_id}' not found.")
            raise
        return OGCCollection(
            id=data.get("id", collection_id),
            title=data.get("title", collection_id),
            description=data.get("description", ""),
            links=data.get("links", []),
            extent=data.get("extent", None),
            item_type=data.get("itemType", None)
        )

    async def get_features(
        self,
        collection_id: str,
        limit: int = 10,
        bbox: Optional[str] = None,
        datetime: Optional[str] = None,
        filter_cql: Optional[str] = None,
    ) -> dict:
        params = {"f": "json", "limit": limit}
        if bbox:
            params["bbox"] = bbox
        if datetime:
            params["datetime"] = datetime
        if filter_cql:
            params["filter"] = filter_cql
        return await self._get(f"/collections/{collection_id}/items", params=params)

    async def get_feature(self, collection_id: str, feature_id: str) -> dict:
        return await self._get(f"/collections/{collection_id}/items/{feature_id}")

    # ── OGC API - Processes ───────────────────────

    async def get_processes(self) -> list[OGCProcess]:
        data = await self._get("/processes")
        processes = []
        for proc in data.get("processes", []):
            processes.append(OGCProcess(
                id=proc.get("id", ""),
                title=proc.get("title", proc.get("id", "")),
                description=proc.get("description", ""),
                version=proc.get("version", "1.0.0"),
                inputs=proc.get("inputs", {}),
                outputs=proc.get("outputs", {}),
                job_control_options=proc.get("jobControlOptions", ["sync-execute"])
            ))
        return processes

    async def get_process(self, process_id: str) -> OGCProcess:
        try:
            data = await self._get(f"/processes/{process_id}")
        except OGCClientError as e:
            if "404" in str(e):
                raise OGCProcessNotFound(
                    f"Process '{process_id}' not found. "
                    f"Use get_processes() to see available processes."
                )
            raise
        return OGCProcess(
            id=data.get("id", process_id),
            title=data.get("title", process_id),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            job_control_options=data.get("jobControlOptions", ["sync-execute"])
        )

    async def execute_process(
        self,
        process_id: str,
        inputs: dict,
        async_execute: bool = False
    ) -> dict:
        headers = {}
        if async_execute:
            headers["Prefer"] = "respond-async"
        return await self._post(
            f"/processes/{process_id}/execution",
            json_data={"inputs": inputs},
            headers=headers
        )

    async def get_job_status(self, job_id: str) -> OGCJob:
        data = await self._get(f"/jobs/{job_id}")
        return OGCJob(
            job_id=data.get("jobID", job_id),
            status=data.get("status", "unknown"),
            type=data.get("type", ""),
            progress=data.get("progress", 0),
            message=data.get("message", ""),
            created=data.get("created", ""),
            updated=data.get("updated", ""),
        )

    async def get_job_results(self, job_id: str) -> dict:
        return await self._get(f"/jobs/{job_id}/results")

    # ══════════════════════════════════════════════
    # NEW Stage 5: OGC API - Records
    # ══════════════════════════════════════════════

    async def search_records(
        self,
        collection_id: str,
        q: Optional[str] = None,
        bbox: Optional[str] = None,
        datetime: Optional[str] = None,
        limit: int = 10,
    ) -> dict:
        """
        Search a metadata catalog for records matching criteria.

        Args:
            collection_id: Catalog collection (e.g., "dutch-metadata")
            q:             Full-text search terms
            bbox:          Bounding box filter "minLon,minLat,maxLon,maxLat"
            datetime:      Temporal filter
            limit:         Max records to return

        Returns:
            GeoJSON FeatureCollection with record items
        """
        params = {"f": "json", "limit": limit}
        if q:
            params["q"] = q
        if bbox:
            params["bbox"] = bbox
        if datetime:
            params["datetime"] = datetime
        return await self._get(f"/collections/{collection_id}/items", params=params)

    async def get_record(
        self,
        collection_id: str,
        record_id: str
    ) -> OGCRecord:
        """
        Get a specific catalog record by ID.

        Args:
            collection_id: Catalog collection (e.g., "dutch-metadata")
            record_id:     Record's unique identifier

        Returns:
            OGCRecord with full metadata
        """
        data = await self._get(
            f"/collections/{collection_id}/items/{record_id}",
            params={"f": "json"}
        )
        props = data.get("properties", {})
        geom = data.get("geometry", {})

        bbox_val = None
        if geom and geom.get("type") == "Polygon":
            coords = geom.get("coordinates", [[]])
            if coords and coords[0]:
                lons = [c[0] for c in coords[0]]
                lats = [c[1] for c in coords[0]]
                bbox_val = [min(lons), min(lats), max(lons), max(lats)]

        return OGCRecord(
            id=data.get("id", record_id),
            title=props.get("title", ""),
            description=props.get("description", ""),
            type=props.get("type", "dataset"),
            keywords=props.get("keywords", []),
            links=data.get("links", []),
            bbox=bbox_val,
            time=props.get("time", None),
            created=props.get("created", None),
            updated=props.get("updated", None),
            properties=props,
        )

    # ══════════════════════════════════════════════
    # NEW Stage 5: OGC API - EDR
    # ══════════════════════════════════════════════

    async def get_edr_collection(
        self,
        collection_id: str
    ) -> OGCEDRCollection:
        """
        Get an EDR collection's metadata including parameter names
        and supported query types.

        Args:
            collection_id: EDR collection (e.g., "icoads-sst")

        Returns:
            OGCEDRCollection with parameters and query capabilities
        """
        data = await self._get(f"/collections/{collection_id}", params={"f": "json"})

        # Parse parameter_names (EDR-specific field)
        parameters = []
        param_names = data.get("parameter_names", data.get("parameter-names", {}))
        if isinstance(param_names, dict):
            for pid, pinfo in param_names.items():
                if isinstance(pinfo, dict):
                    unit_info = pinfo.get("unit", {})
                    unit_label = ""
                    if isinstance(unit_info, dict):
                        unit_label = unit_info.get("label", unit_info.get("symbol", ""))
                        if isinstance(unit_label, dict):
                            unit_label = unit_label.get("value", "")
                    elif isinstance(unit_info, str):
                        unit_label = unit_info

                    obs_prop = pinfo.get("observedProperty", {})
                    parameters.append(OGCEDRParameter(
                        id=pid,
                        label=obs_prop.get("label", pid) if isinstance(obs_prop, dict) else pid,
                        description=obs_prop.get("description", "") if isinstance(obs_prop, dict) else "",
                        unit=unit_label or None,
                        unit_label=unit_label or None,
                    ))

        # Parse supported query types from data_queries or links
        query_types = []
        data_queries = data.get("data_queries", {})
        if isinstance(data_queries, dict) and data_queries:
            query_types = list(data_queries.keys())
        else:
            # Fallback: infer from links
            for link in data.get("links", []):
                href = link.get("href", "")
                for qt in ["position", "area", "cube", "trajectory", "radius", "corridor", "locations"]:
                    if f"/{qt}" in href and qt not in query_types:
                        query_types.append(qt)

        # Parse output formats
        output_formats = []
        if isinstance(data_queries, dict):
            for qt_info in data_queries.values():
                if isinstance(qt_info, dict):
                    link = qt_info.get("link", {})
                    variables = link.get("variables", {})
                    fmts = variables.get("output_formats", [])
                    for fmt in fmts:
                        if fmt not in output_formats:
                            output_formats.append(fmt)

        return OGCEDRCollection(
            id=data.get("id", collection_id),
            title=data.get("title", collection_id),
            description=data.get("description", ""),
            parameters=parameters,
            query_types=query_types,
            extent=data.get("extent", None),
            crs=data.get("crs", None),
            output_formats=output_formats or None,
        )

    async def query_edr_position(
        self,
        collection_id: str,
        coords: str,
        parameter_name: Optional[str] = None,
        datetime: Optional[str] = None,
        z: Optional[str] = None,
    ) -> dict:
        """
        Query environmental data at a specific point.

        Args:
            collection_id:  EDR collection (e.g., "icoads-sst")
            coords:         WKT POINT (e.g., "POINT(33 33)")
            parameter_name: Comma-separated parameter names (e.g., "SST,AIRT")
            datetime:       Temporal filter
            z:              Vertical level

        Returns:
            CoverageJSON or JSON response
        """
        params = {"f": "json", "coords": coords}
        if parameter_name:
            params["parameter-name"] = parameter_name
        if datetime:
            params["datetime"] = datetime
        if z:
            params["z"] = z
        return await self._get(f"/collections/{collection_id}/position", params=params)

    async def query_edr_area(
        self,
        collection_id: str,
        coords: str,
        parameter_name: Optional[str] = None,
        datetime: Optional[str] = None,
        z: Optional[str] = None,
    ) -> dict:
        """
        Query environmental data within a polygon area.

        Args:
            collection_id:  EDR collection
            coords:         WKT POLYGON
            parameter_name: Comma-separated parameter names
            datetime:       Temporal filter
            z:              Vertical level

        Returns:
            CoverageJSON or JSON response
        """
        params = {"f": "json", "coords": coords}
        if parameter_name:
            params["parameter-name"] = parameter_name
        if datetime:
            params["datetime"] = datetime
        if z:
            params["z"] = z
        return await self._get(f"/collections/{collection_id}/area", params=params)
