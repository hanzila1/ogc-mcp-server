"""
Tests for ogc_tiles.py — OGC API Tiles support module.

All tests are offline — no real HTTP calls.
Tests cover data classes, parsers, and format functions.

License: Apache Software License, Version 2.0
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ogc_mcp.ogc_tiles import (
    OGCTileSet,
    OGCTileSetInfo,
    _parse_zoom_levels,
    _parse_formats,
    format_tilesets,
    format_tile_metadata,
)


# ─────────────────────────────────────────────
# OGCTileSet
# ─────────────────────────────────────────────

class TestOGCTileSet:

    def test_basic_creation(self):
        ts = OGCTileSet(
            tileset_id="WebMercatorQuad",
            title="Web Mercator",
            tiling_scheme="WebMercatorQuad",
            data_type="vector",
        )
        assert ts.tileset_id == "WebMercatorQuad"
        assert ts.data_type == "vector"
        assert ts.formats == []
        assert ts.min_zoom is None
        assert ts.max_zoom is None

    def test_full_creation(self):
        ts = OGCTileSet(
            tileset_id="WorldCRS84Quad",
            title="World CRS84",
            tiling_scheme="WorldCRS84Quad",
            data_type="map",
            min_zoom=0,
            max_zoom=18,
            formats=["image/png", "image/jpeg"],
            crs="http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        )
        assert ts.min_zoom == 0
        assert ts.max_zoom == 18
        assert "image/png" in ts.formats


# ─────────────────────────────────────────────
# OGCTileSetInfo
# ─────────────────────────────────────────────

class TestOGCTileSetInfo:

    def test_empty_tilesets(self):
        info = OGCTileSetInfo(
            collection_id="lakes",
            collection_title="Lakes of Europe",
        )
        assert info.tilesets == []
        assert info.supports_vector_tiles is False
        assert info.supports_map_tiles is False

    def test_with_tilesets(self):
        ts = OGCTileSet(
            tileset_id="WebMercatorQuad",
            title="Web Mercator",
            tiling_scheme="WebMercatorQuad",
            data_type="vector",
        )
        info = OGCTileSetInfo(
            collection_id="lakes",
            collection_title="Lakes",
            tilesets=[ts],
            supports_vector_tiles=True,
        )
        assert len(info.tilesets) == 1
        assert info.supports_vector_tiles is True


# ─────────────────────────────────────────────
# _parse_zoom_levels
# ─────────────────────────────────────────────

class TestParseZoomLevels:

    def test_no_limits_returns_none(self):
        tileset = {}
        min_z, max_z = _parse_zoom_levels(tileset)
        assert min_z is None
        assert max_z is None

    def test_empty_limits_returns_none(self):
        tileset = {"tileMatrixSetLimits": []}
        min_z, max_z = _parse_zoom_levels(tileset)
        assert min_z is None
        assert max_z is None

    def test_parses_zoom_range(self):
        tileset = {
            "tileMatrixSetLimits": [
                {"tileMatrix": "WebMercatorQuad:0"},
                {"tileMatrix": "WebMercatorQuad:5"},
                {"tileMatrix": "WebMercatorQuad:12"},
            ]
        }
        min_z, max_z = _parse_zoom_levels(tileset)
        assert min_z == 0
        assert max_z == 12

    def test_single_zoom_level(self):
        tileset = {
            "tileMatrixSetLimits": [
                {"tileMatrix": "WebMercatorQuad:8"},
            ]
        }
        min_z, max_z = _parse_zoom_levels(tileset)
        assert min_z == 8
        assert max_z == 8


# ─────────────────────────────────────────────
# _parse_formats
# ─────────────────────────────────────────────

class TestParseFormats:

    def test_no_links_returns_empty(self):
        tileset = {}
        formats = _parse_formats(tileset)
        assert formats == []

    def test_extracts_media_types(self):
        tileset = {
            "links": [
                {"rel": "item", "type": "application/vnd.mapbox-vector-tile"},
                {"rel": "item", "type": "image/png"},
            ]
        }
        formats = _parse_formats(tileset)
        assert "application/vnd.mapbox-vector-tile" in formats
        assert "image/png" in formats

    def test_deduplicates(self):
        tileset = {
            "links": [
                {"rel": "item", "type": "image/png"},
                {"rel": "alternate", "type": "image/png"},
            ]
        }
        formats = _parse_formats(tileset)
        assert formats.count("image/png") == 1

    def test_skips_links_without_type(self):
        tileset = {
            "links": [
                {"rel": "item"},
                {"rel": "item", "type": "image/png"},
            ]
        }
        formats = _parse_formats(tileset)
        assert formats == ["image/png"]


# ─────────────────────────────────────────────
# format_tilesets
# ─────────────────────────────────────────────

class TestFormatTilesets:

    def test_empty_tilesets_message(self):
        info = OGCTileSetInfo(
            collection_id="lakes",
            collection_title="Lakes",
            tilesets=[],
        )
        result = format_tilesets(info)
        assert "does not expose any tilesets" in result
        assert "lakes" in result

    def test_formats_single_tileset(self):
        ts = OGCTileSet(
            tileset_id="WebMercatorQuad",
            title="Web Mercator Quad",
            tiling_scheme="WebMercatorQuad",
            data_type="vector",
            min_zoom=0,
            max_zoom=14,
            formats=["application/vnd.mapbox-vector-tile"],
        )
        info = OGCTileSetInfo(
            collection_id="lakes",
            collection_title="Lakes of Europe",
            tilesets=[ts],
            supports_vector_tiles=True,
        )
        result = format_tilesets(info)
        assert "WebMercatorQuad" in result
        assert "vector" in result
        assert "0" in result
        assert "14" in result
        assert "vector tiles" in result

    def test_shows_vector_support(self):
        info = OGCTileSetInfo(
            collection_id="rivers",
            collection_title="Rivers",
            tilesets=[OGCTileSet("WebMercatorQuad","WMQ","WebMercatorQuad","vector")],
            supports_vector_tiles=True,
            supports_map_tiles=False,
        )
        result = format_tilesets(info)
        assert "vector tiles" in result

    def test_shows_map_support(self):
        info = OGCTileSetInfo(
            collection_id="sat",
            collection_title="Satellite",
            tilesets=[OGCTileSet("WebMercatorQuad","WMQ","WebMercatorQuad","map")],
            supports_vector_tiles=False,
            supports_map_tiles=True,
        )
        result = format_tilesets(info)
        assert "map/raster tiles" in result


# ─────────────────────────────────────────────
# format_tile_metadata
# ─────────────────────────────────────────────

class TestFormatTileMetadata:

    def test_with_tile_url_template(self):
        metadata = {
            "links": [
                {
                    "rel": "item",
                    "href": "https://example.com/collections/lakes/tiles/WebMercatorQuad/{tileMatrix}/{tileRow}/{tileCol}",
                    "type": "application/vnd.mapbox-vector-tile"
                }
            ]
        }
        result = format_tile_metadata(metadata, "lakes", "WebMercatorQuad")
        assert "tileMatrix" in result
        assert "tileRow" in result
        assert "example.com" in result

    def test_without_tile_url(self):
        metadata = {"links": []}
        result = format_tile_metadata(metadata, "lakes", "WebMercatorQuad")
        assert "No tile URL template found" in result

    def test_shows_collection_and_tileset(self):
        metadata = {}
        result = format_tile_metadata(metadata, "lakes", "WebMercatorQuad")
        assert "WebMercatorQuad" in result
        assert "lakes" in result
