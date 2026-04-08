"""
Catalog-of-Catalogs Discovery — autonomous OGC server discovery via Records API.

This module implements the "catalog-of-catalogs" capability praised by the
52°North mentors during the GSoC 2026 pre-proposal period.

How it works:
    1. Start with a set of known seed OGC servers (the registry)
    2. Given a user topic (e.g. "flood risk", "urban heat islands"),
       query OGC API Records endpoints on seed servers
    3. Parse the catalog results — records often contain links to
       other OGC API servers and datasets
    4. Register newly discovered servers, expanding the registry dynamically

This transforms the system from knowing 3 hardcoded servers to potentially
discovering hundreds of OGC servers autonomously from a topic alone.

New MCP Tools this enables (wired in server.py):
    - discover_servers_by_topic(topic)
    - list_known_servers()

License: Apache Software License, Version 2.0
Author: Hanzila Bin Younus — GSoC 2026 @ 52°North
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────

@dataclass
class OGCServerEntry:
    """
    Represents a known or discovered OGC API server.

    Fields:
        url:          Base URL of the OGC API server
        name:         Human-readable name
        description:  What data this server provides
        capabilities: Which OGC API types it supports
        source:       How it was discovered (seed / catalog-discovery)
        catalog_id:   The Records collection ID if this server has a catalog
    """
    url: str
    name: str
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    source: str = "seed"
    catalog_id: Optional[str] = None


# ─────────────────────────────────────────────
# Seed server registry — the known starting points
# ─────────────────────────────────────────────

SEED_SERVERS: list[OGCServerEntry] = [
    OGCServerEntry(
        url="https://demo.pygeoapi.io/master",
        name="pygeoapi demo",
        description="Netherlands windmills, castles, lakes. NOAA ocean EDR. Dutch metadata catalog.",
        capabilities=["features", "records", "edr", "processes"],
        source="seed",
        catalog_id="dutch-metadata",
    ),
    OGCServerEntry(
        url="https://maps.gnosis.earth/ogcapi",
        name="Gnosis Earth",
        description="749 global collections. NaturalEarth rivers, countries, elevation. Independent OGC implementation.",
        capabilities=["features", "processes"],
        source="seed",
        catalog_id=None,
    ),
    OGCServerEntry(
        url="http://localhost:5000",
        name="Local Docker backend",
        description="Custom Münster parks dataset. Cool spot analysis process. Geospatial buffer process.",
        capabilities=["features", "processes"],
        source="seed",
        catalog_id=None,
    ),
]


# ─────────────────────────────────────────────
# Server Registry — manages known + discovered servers
# ─────────────────────────────────────────────

class ServerRegistry:
    """
    Manages the list of known OGC API servers.

    Starts with SEED_SERVERS and grows dynamically
    as catalog-of-catalogs discovery finds new servers.
    """

    def __init__(self):
        self._servers: dict[str, OGCServerEntry] = {
            s.url.rstrip("/"): s for s in SEED_SERVERS
        }

    def get_all(self) -> list[OGCServerEntry]:
        """Return all known servers."""
        return list(self._servers.values())

    def get_seed_servers(self) -> list[OGCServerEntry]:
        """Return only the original seed servers."""
        return [s for s in self._servers.values() if s.source == "seed"]

    def get_discovered_servers(self) -> list[OGCServerEntry]:
        """Return only servers found via catalog discovery."""
        return [s for s in self._servers.values() if s.source == "catalog-discovery"]

    def register(self, server: OGCServerEntry) -> bool:
        """
        Add a newly discovered server to the registry.

        Returns True if it was new, False if already known.
        """
        key = server.url.rstrip("/")
        if key in self._servers:
            return False
        self._servers[key] = server
        logger.info(f"New server registered: {server.name} ({server.url})")
        return True

    def find_by_capability(self, capability: str) -> list[OGCServerEntry]:
        """Return servers that support a given OGC API type."""
        return [
            s for s in self._servers.values()
            if capability.lower() in [c.lower() for c in s.capabilities]
        ]

    def format_for_llm(self) -> str:
        """Format the full registry as LLM-readable text."""
        servers = self.get_all()
        if not servers:
            return "No OGC servers registered."

        seed = [s for s in servers if s.source == "seed"]
        discovered = [s for s in servers if s.source == "catalog-discovery"]

        lines = [f"Known OGC API servers ({len(servers)} total):", ""]

        if seed:
            lines.append(f"Seed servers ({len(seed)}):")
            for s in seed:
                caps = ", ".join(s.capabilities) if s.capabilities else "unknown"
                lines.append(f"  [{s.name}] {s.url}")
                lines.append(f"    {s.description}")
                lines.append(f"    Capabilities: {caps}")
                if s.catalog_id:
                    lines.append(f"    Catalog ID: {s.catalog_id}")
                lines.append("")

        if discovered:
            lines.append(f"Discovered via catalog-of-catalogs ({len(discovered)}):")
            for s in discovered:
                caps = ", ".join(s.capabilities) if s.capabilities else "unknown"
                lines.append(f"  [{s.name}] {s.url}")
                lines.append(f"    {s.description}")
                lines.append(f"    Capabilities: {caps}")
                lines.append("")

        return "\n".join(lines)


# ─────────────────────────────────────────────
# Global registry instance
# ─────────────────────────────────────────────

_registry = ServerRegistry()


def get_registry() -> ServerRegistry:
    """Return the global server registry."""
    return _registry


# ─────────────────────────────────────────────
# Link parsing — extract OGC server URLs from catalog records
# ─────────────────────────────────────────────

_OGC_LINK_RELS = {
    "item",
    "canonical",
    "related",
    "service",
    "enclosure",
    "http://www.opengis.net/def/rel/ogc/1.0/ogc-rel:data",
}

_OGC_URL_HINTS = [
    "/ogcapi", "/wfs", "/wms", "/api",
    "pygeoapi", "geoserver", "mapserver",
    "gnosis", "ldproxy",
]


def _looks_like_ogc_server(url: str) -> bool:
    """Heuristic: does this URL look like an OGC API server base URL?"""
    url_lower = url.lower()
    # Must be http/https
    if not url_lower.startswith("http"):
        return False
    # Skip obvious non-servers
    skip = [".pdf", ".zip", ".xml", ".json", ".html", ".png",
            "mailto:", "doi.org", "creativecommons"]
    if any(s in url_lower for s in skip):
        return False
    # Positive hints
    return any(hint in url_lower for hint in _OGC_URL_HINTS)


def _extract_server_urls_from_record(record: dict) -> list[str]:
    """
    Extract potential OGC server URLs from a single catalog record (GeoJSON Feature).

    Looks in:
    - record["links"] — standard OGC Records link objects
    - record["properties"]["links"] — some implementations put links here
    - record["properties"]["url"] — direct URL property
    """
    candidate_urls = []

    # Check top-level links — always apply URL filter regardless of rel
    for link in record.get("links", []):
        href = link.get("href", "")
        if href and _looks_like_ogc_server(href):
            candidate_urls.append(href)

    # Check properties.links
    props = record.get("properties", {})
    for link in props.get("links", []):
        href = link.get("href", "") if isinstance(link, dict) else str(link)
        if href and _looks_like_ogc_server(href):
            candidate_urls.append(href)

    # Check properties.url directly
    direct_url = props.get("url", props.get("href", ""))
    if direct_url and _looks_like_ogc_server(direct_url):
        candidate_urls.append(direct_url)

    return list(set(candidate_urls))


def _record_to_server_entry(record: dict, url: str) -> OGCServerEntry:
    """Build an OGCServerEntry from a catalog record and a discovered URL."""
    props = record.get("properties", {})
    title = props.get("title", url)
    description = props.get("description", "")
    keywords = props.get("keywords", [])
    if keywords and not description:
        description = f"Keywords: {', '.join(str(k) for k in keywords[:5])}"

    return OGCServerEntry(
        url=url.rstrip("/"),
        name=title[:80],
        description=description[:200],
        capabilities=[],
        source="catalog-discovery",
    )


# ─────────────────────────────────────────────
# Core discovery function
# ─────────────────────────────────────────────

async def discover_servers_from_topic(
    topic: str,
    timeout: float = 15.0,
) -> list[OGCServerEntry]:
    """
    Discover new OGC API servers by searching catalog endpoints on known servers.

    For each seed server that has a catalog (catalog_id is set):
        1. Query GET /collections/{catalog_id}/items?q={topic}
        2. Parse each record for links pointing to OGC servers
        3. Register newly found servers in the global registry

    Args:
        topic:   Natural language topic, e.g. "flood risk Netherlands"
        timeout: HTTP timeout in seconds

    Returns:
        List of newly discovered OGCServerEntry objects (not including already known)
    """
    registry = get_registry()
    newly_discovered: list[OGCServerEntry] = []

    catalog_servers = [s for s in registry.get_seed_servers() if s.catalog_id]
    if not catalog_servers:
        logger.warning("No seed servers with catalog_id — cannot run catalog discovery")
        return []

    logger.info(f"Catalog-of-catalogs discovery: topic='{topic}', "
                f"searching {len(catalog_servers)} catalog(s)")

    async with httpx.AsyncClient(timeout=timeout) as client:
        for server in catalog_servers:
            catalog_url = (
                f"{server.url.rstrip('/')}"
                f"/collections/{server.catalog_id}/items"
            )
            params = {"q": topic, "f": "json", "limit": 20}

            try:
                response = await client.get(catalog_url, params=params)
                response.raise_for_status()
                data = response.json()
            except httpx.ConnectError:
                logger.warning(f"Cannot reach catalog at {server.url}")
                continue
            except httpx.TimeoutException:
                logger.warning(f"Timeout querying catalog at {server.url}")
                continue
            except Exception as e:
                logger.warning(f"Error querying {catalog_url}: {e}")
                continue

            features = data.get("features", [])
            logger.info(f"  {server.name}: {len(features)} records for '{topic}'")

            for record in features:
                candidate_urls = _extract_server_urls_from_record(record)
                for url in candidate_urls:
                    entry = _record_to_server_entry(record, url)
                    is_new = registry.register(entry)
                    if is_new:
                        newly_discovered.append(entry)
                        logger.info(f"  Discovered: {entry.name} → {entry.url}")

    return newly_discovered


# ─────────────────────────────────────────────
# MCP-ready format functions
# ─────────────────────────────────────────────

def format_discovery_results(
    topic: str,
    newly_discovered: list[OGCServerEntry],
) -> str:
    """Format catalog-of-catalogs discovery results for LLM consumption."""
    registry = get_registry()
    all_servers = registry.get_all()

    if not newly_discovered:
        lines = [
            f"Catalog-of-catalogs search for '{topic}' complete.",
            f"No new servers discovered beyond the {len(all_servers)} already known.",
            "",
            "Known servers with relevant data may still have matching collections.",
            "Try get_collections() on the known servers or search_catalog() directly.",
        ]
        return "\n".join(lines)

    lines = [
        f"Catalog-of-catalogs discovery for '{topic}':",
        f"Found {len(newly_discovered)} new OGC server(s):",
        "",
    ]
    for s in newly_discovered:
        lines.append(f"  [{s.name}]")
        lines.append(f"  URL: {s.url}")
        if s.description:
            lines.append(f"  {s.description}")
        lines.append(f"  Use discover_ogc_server(server_url='{s.url}') to explore.")
        lines.append("")

    lines.append(f"Total known servers now: {len(all_servers)}")
    return "\n".join(lines)


def format_known_servers() -> str:
    """Format all known servers for LLM consumption."""
    return get_registry().format_for_llm()
