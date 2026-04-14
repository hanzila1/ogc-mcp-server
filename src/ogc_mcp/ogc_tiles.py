"""
OGC API - Tiles support module.

Extends the ogc-mcp-server with OGC API Tiles capability.
This is a new, standalone module — zero changes to existing files.

OGC API - Tiles allows access to tiled geospatial data:
- Vector tiles (Mapbox Vector Tiles format)
- Raster tiles (PNG, JPEG)
- Coverage tiles

New MCP Tools added (wired via server.py):
    - get_tilesets(server_url, collection_id)
    - get_tile(server_url, collection_id, tileset_id, z, x, y)

Reference: https://ogcapi.ogc.org/tiles/

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
class OGCTileSet:
    """
    Represents a single OGC API TileSet.

    A TileSet defines how tiles are organized — the tiling scheme,
    supported formats, and zoom level range.
    """
    tileset_id: str
    title: str
    tiling_scheme: str           # e.g. "WebMercatorQuad", "WorldCRS84Quad"
    data_type: str               # "vector", "map", "coverage"
    links: list[dict] = field(default_factory=list)
    min_zoom: Optional[int] = None
    max_zoom: Optional[int] = None
    formats: list[str] = field(default_factory=list)
    crs: Optional[str] = None


@dataclass
class OGCTileSetInfo:
    """
    Metadata about a collection's tile capabilities.
    """
    collection_id: str
    collection_title: str
    tilesets: list[OGCTileSet] = field(default_factory=list)
    supports_vector_tiles: bool = False
    supports_map_tiles: bool = False


# ─────────────────────────────────────────────
# Tiles HTTP client functions
# ─────────────────────────────────────────────

async def fetch_tilesets(
    base_url: str,
    collection_id: str,
    timeout: float = 15.0,
) -> OGCTileSetInfo:
    """
    Fetch available tilesets for a collection.

    Calls GET /collections/{collectionId}/tiles

    Args:
        base_url:      OGC API server base URL
        collection_id: Collection to query tilesets for
        timeout:       HTTP timeout in seconds

    Returns:
        OGCTileSetInfo with all available tilesets
    """
    url = f"{base_url.rstrip('/')}/collections/{collection_id}/tiles"
    params = {"f": "json"}

    tilesets = []
    supports_vector = False
    supports_map = False

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.ConnectError:
            raise ConnectionError(f"Cannot connect to {base_url}")
        except httpx.TimeoutException:
            raise TimeoutError(f"Timeout connecting to {base_url}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(
                    f"Collection '{collection_id}' does not support tiles. "
                    f"Use get_collections() to find tile-enabled collections."
                )
            raise RuntimeError(f"HTTP {e.response.status_code} from {url}")

        # Parse tilesets from response
        # OGC API Tiles response has a "tilesets" array
        raw_tilesets = data.get("tilesets", [])

        for ts in raw_tilesets:
            tileset_id = ts.get("tileMatrixSetURI", ts.get("id", "unknown"))
            # Extract just the scheme name from full URI
            if "/" in tileset_id:
                tileset_id = tileset_id.split("/")[-1]

            data_type = ts.get("dataType", ts.get("type", "map"))
            if data_type == "vector":
                supports_vector = True
            elif data_type in ("map", "raster"):
                supports_map = True

            # Parse zoom levels from links
            min_zoom, max_zoom = _parse_zoom_levels(ts)

            # Parse formats from links
            formats = _parse_formats(ts)

            tilesets.append(OGCTileSet(
                tileset_id=tileset_id,
                title=ts.get("title", tileset_id),
                tiling_scheme=tileset_id,
                data_type=data_type,
                links=ts.get("links", []),
                min_zoom=min_zoom,
                max_zoom=max_zoom,
                formats=formats,
                crs=ts.get("crs", None),
            ))

    # Also check collection metadata for tile support
    collection_title = collection_id
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            col_response = await client.get(
                f"{base_url.rstrip('/')}/collections/{collection_id}",
                params={"f": "json"}
            )
            if col_response.status_code == 200:
                col_data = col_response.json()
                collection_title = col_data.get("title", collection_id)
    except Exception:
        pass

    return OGCTileSetInfo(
        collection_id=collection_id,
        collection_title=collection_title,
        tilesets=tilesets,
        supports_vector_tiles=supports_vector,
        supports_map_tiles=supports_map,
    )


async def fetch_tile_metadata(
    base_url: str,
    collection_id: str,
    tileset_id: str,
    timeout: float = 15.0,
) -> dict:
    """
    Fetch metadata for a specific tileset.

    Calls GET /collections/{collectionId}/tiles/{tileMatrixSetId}

    Returns raw JSON metadata including tile URL template.
    """
    url = (
        f"{base_url.rstrip('/')}"
        f"/collections/{collection_id}"
        f"/tiles/{tileset_id}"
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(url, params={"f": "json"})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"HTTP {e.response.status_code} fetching tileset metadata")


# ─────────────────────────────────────────────
# Helper parsers
# ─────────────────────────────────────────────

def _parse_zoom_levels(tileset: dict) -> tuple[Optional[int], Optional[int]]:
    """Extract min/max zoom from tileset links or tileMatrixSetLimits."""
    limits = tileset.get("tileMatrixSetLimits", [])
    if not limits:
        return None, None
    try:
        zoom_levels = [
            int(lim.get("tileMatrix", "0").split(":")[-1])
            for lim in limits
            if "tileMatrix" in lim
        ]
        if zoom_levels:
            return min(zoom_levels), max(zoom_levels)
    except (ValueError, AttributeError):
        pass
    return None, None


def _parse_formats(tileset: dict) -> list[str]:
    """Extract supported tile formats from tileset links."""
    formats = []
    for link in tileset.get("links", []):
        media_type = link.get("type", "")
        if media_type and media_type not in formats:
            formats.append(media_type)
    return formats


# ─────────────────────────────────────────────
# MCP-ready format functions
# ─────────────────────────────────────────────

def format_tilesets(info: OGCTileSetInfo) -> str:
    """Format OGCTileSetInfo for LLM consumption."""
    if not info.tilesets:
        return (
            f"Collection '{info.collection_id}' does not expose any tilesets. "
            f"Not all OGC API servers support the Tiles extension."
        )

    lines = [
        f"Tilesets for collection: {info.collection_title} ({info.collection_id})",
        f"Total tilesets: {len(info.tilesets)}",
        "",
    ]

    if info.supports_vector_tiles:
        lines.append("  Supports: vector tiles (MVT)")
    if info.supports_map_tiles:
        lines.append("  Supports: map/raster tiles")
    lines.append("")

    for ts in info.tilesets:
        lines.append(f"  [{ts.tileset_id}] {ts.title}")
        lines.append(f"    Type: {ts.data_type}")
        lines.append(f"    Tiling scheme: {ts.tiling_scheme}")
        if ts.min_zoom is not None and ts.max_zoom is not None:
            lines.append(f"    Zoom levels: {ts.min_zoom} – {ts.max_zoom}")
        if ts.formats:
            lines.append(f"    Formats: {', '.join(ts.formats)}")
        lines.append("")

    lines.append(
        "To get tile URL template: use get_tile_metadata("
        f"collection_id='{info.collection_id}', tileset_id='<id>')"
    )
    return "\n".join(lines)


def format_tile_metadata(metadata: dict, collection_id: str, tileset_id: str) -> str:
    """Format raw tileset metadata for LLM consumption."""
    lines = [
        f"Tileset metadata: {tileset_id} / {collection_id}",
        "",
    ]

    # Extract tile URL template from links
    tile_url_template = None
    for link in metadata.get("links", []):
        rel = link.get("rel", "")
        if rel in ("item", "http://www.opengis.net/def/rel/ogc/1.0/map"):
            tile_url_template = link.get("href", "")
            break

    if tile_url_template:
        lines.append(f"Tile URL template:")
        lines.append(f"  {tile_url_template}")
        lines.append("")
        lines.append(
            "Replace {tileMatrix} with zoom level (e.g. 10), "
            "{tileRow} with row, {tileCol} with column."
        )
    else:
        lines.append("No tile URL template found in metadata.")
        links = metadata.get("links", [])
        if links:
            lines.append(f"Available links ({len(links)}):")
            for link in links[:5]:
                lines.append(f"  {link.get('rel','?')}: {link.get('href','')}")

    return "\n".join(lines)
