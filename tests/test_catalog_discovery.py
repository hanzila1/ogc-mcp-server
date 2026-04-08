"""
Tests for catalog_discovery.py — catalog-of-catalogs discovery module.

These tests cover:
- ServerRegistry: register, find, format
- Link parsing: _extract_server_urls_from_record
- OGC server URL heuristic: _looks_like_ogc_server
- format functions: format_known_servers, format_discovery_results

All tests are offline (no real HTTP calls) — they test the logic only.

License: Apache Software License, Version 2.0
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ogc_mcp.catalog_discovery import (
    OGCServerEntry,
    ServerRegistry,
    SEED_SERVERS,
    get_registry,
    _looks_like_ogc_server,
    _extract_server_urls_from_record,
    _record_to_server_entry,
    format_discovery_results,
    format_known_servers,
)


# ─────────────────────────────────────────────
# OGCServerEntry
# ─────────────────────────────────────────────

class TestOGCServerEntry:

    def test_basic_creation(self):
        entry = OGCServerEntry(
            url="https://example.com/ogcapi",
            name="Test Server",
        )
        assert entry.url == "https://example.com/ogcapi"
        assert entry.name == "Test Server"
        assert entry.description == ""
        assert entry.capabilities == []
        assert entry.source == "seed"
        assert entry.catalog_id is None

    def test_full_creation(self):
        entry = OGCServerEntry(
            url="https://demo.pygeoapi.io/master",
            name="pygeoapi demo",
            description="Netherlands data",
            capabilities=["features", "records"],
            source="catalog-discovery",
            catalog_id="dutch-metadata",
        )
        assert entry.capabilities == ["features", "records"]
        assert entry.source == "catalog-discovery"
        assert entry.catalog_id == "dutch-metadata"


# ─────────────────────────────────────────────
# ServerRegistry
# ─────────────────────────────────────────────

class TestServerRegistry:

    def setup_method(self):
        """Fresh registry for each test."""
        self.registry = ServerRegistry()

    def test_seeds_loaded(self):
        servers = self.registry.get_all()
        assert len(servers) == len(SEED_SERVERS)

    def test_seed_servers_only(self):
        seeds = self.registry.get_seed_servers()
        assert all(s.source == "seed" for s in seeds)

    def test_no_discovered_initially(self):
        discovered = self.registry.get_discovered_servers()
        assert discovered == []

    def test_register_new_server(self):
        new = OGCServerEntry(
            url="https://new-server.example.com/api",
            name="New Server",
            source="catalog-discovery",
        )
        result = self.registry.register(new)
        assert result is True
        assert len(self.registry.get_all()) == len(SEED_SERVERS) + 1

    def test_register_duplicate_ignored(self):
        existing_url = SEED_SERVERS[0].url
        duplicate = OGCServerEntry(
            url=existing_url,
            name="Duplicate",
        )
        result = self.registry.register(duplicate)
        assert result is False
        assert len(self.registry.get_all()) == len(SEED_SERVERS)

    def test_register_trailing_slash_normalized(self):
        new = OGCServerEntry(
            url="https://new-server.example.com/api/",
            name="Trailing Slash Server",
            source="catalog-discovery",
        )
        result = self.registry.register(new)
        assert result is True

        duplicate = OGCServerEntry(
            url="https://new-server.example.com/api",
            name="Same Without Slash",
            source="catalog-discovery",
        )
        result2 = self.registry.register(duplicate)
        assert result2 is False

    def test_find_by_capability(self):
        servers_with_records = self.registry.find_by_capability("records")
        assert len(servers_with_records) >= 1
        assert all("records" in s.capabilities for s in servers_with_records)

    def test_find_by_capability_case_insensitive(self):
        result_lower = self.registry.find_by_capability("features")
        result_upper = self.registry.find_by_capability("Features")
        assert len(result_lower) == len(result_upper)

    def test_format_for_llm_contains_server_names(self):
        text = self.registry.format_for_llm()
        assert "pygeoapi" in text.lower() or "demo" in text.lower()
        assert "Known OGC API servers" in text

    def test_format_for_llm_shows_discovered(self):
        self.registry.register(OGCServerEntry(
            url="https://discovered.example.com/ogcapi",
            name="Discovered Server",
            description="Found via catalog search",
            source="catalog-discovery",
        ))
        text = self.registry.format_for_llm()
        assert "Discovered via catalog-of-catalogs" in text
        assert "Discovered Server" in text


# ─────────────────────────────────────────────
# URL heuristic
# ─────────────────────────────────────────────

class TestLooksLikeOGCServer:

    def test_pygeoapi_url(self):
        assert _looks_like_ogc_server("https://demo.pygeoapi.io/master") is True

    def test_gnosis_url(self):
        assert _looks_like_ogc_server("https://maps.gnosis.earth/ogcapi") is True

    def test_ogcapi_path(self):
        assert _looks_like_ogc_server("https://example.com/ogcapi") is True

    def test_geoserver_url(self):
        assert _looks_like_ogc_server("https://example.com/geoserver/wfs") is True

    def test_pdf_rejected(self):
        assert _looks_like_ogc_server("https://example.com/document.pdf") is False

    def test_zip_rejected(self):
        assert _looks_like_ogc_server("https://example.com/data.zip") is False

    def test_doi_rejected(self):
        assert _looks_like_ogc_server("https://doi.org/10.1234/something") is False

    def test_mailto_rejected(self):
        assert _looks_like_ogc_server("mailto:info@example.com") is False

    def test_plain_website_rejected(self):
        assert _looks_like_ogc_server("https://example.com/about") is False

    def test_non_http_rejected(self):
        assert _looks_like_ogc_server("ftp://example.com/data") is False


# ─────────────────────────────────────────────
# Link extraction from records
# ─────────────────────────────────────────────

class TestExtractServerUrls:

    def test_extracts_from_links(self):
        record = {
            "id": "test-record",
            "properties": {"title": "Test"},
            "links": [
                {"rel": "related", "href": "https://example.com/ogcapi"},
                {"rel": "canonical", "href": "https://example.com/doc.pdf"},
            ]
        }
        urls = _extract_server_urls_from_record(record)
        assert "https://example.com/ogcapi" in urls
        assert "https://example.com/doc.pdf" not in urls

    def test_extracts_from_properties_url(self):
        record = {
            "id": "test-record",
            "properties": {
                "title": "Test",
                "url": "https://example.com/pygeoapi"
            },
            "links": []
        }
        urls = _extract_server_urls_from_record(record)
        assert "https://example.com/pygeoapi" in urls

    def test_empty_record_returns_empty(self):
        record = {"id": "empty", "properties": {}, "links": []}
        urls = _extract_server_urls_from_record(record)
        assert urls == []

    def test_deduplicates_urls(self):
        record = {
            "id": "test",
            "properties": {"url": "https://example.com/ogcapi"},
            "links": [
                {"rel": "related", "href": "https://example.com/ogcapi"}
            ]
        }
        urls = _extract_server_urls_from_record(record)
        assert urls.count("https://example.com/ogcapi") == 1


# ─────────────────────────────────────────────
# Record to server entry
# ─────────────────────────────────────────────

class TestRecordToServerEntry:

    def test_basic_conversion(self):
        record = {
            "properties": {
                "title": "Flood Risk Netherlands",
                "description": "Flood risk dataset for NL",
            }
        }
        entry = _record_to_server_entry(record, "https://example.com/ogcapi")
        assert entry.url == "https://example.com/ogcapi"
        assert entry.name == "Flood Risk Netherlands"
        assert entry.description == "Flood risk dataset for NL"
        assert entry.source == "catalog-discovery"

    def test_uses_keywords_when_no_description(self):
        record = {
            "properties": {
                "title": "Some Dataset",
                "keywords": ["flood", "netherlands", "risk"],
            }
        }
        entry = _record_to_server_entry(record, "https://example.com/ogcapi")
        assert "flood" in entry.description.lower()

    def test_url_stripped(self):
        record = {"properties": {"title": "Test"}}
        entry = _record_to_server_entry(record, "https://example.com/ogcapi/")
        assert not entry.url.endswith("/")


# ─────────────────────────────────────────────
# Format functions
# ─────────────────────────────────────────────

class TestFormatFunctions:

    def test_format_known_servers_returns_string(self):
        result = format_known_servers()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_discovery_no_results(self):
        result = format_discovery_results("flood risk", [])
        assert "flood risk" in result
        assert "No new servers" in result

    def test_format_discovery_with_results(self):
        new_servers = [
            OGCServerEntry(
                url="https://flood.example.com/ogcapi",
                name="Flood Data Server",
                description="Flood risk data for Europe",
                source="catalog-discovery",
            )
        ]
        result = format_discovery_results("flood risk", new_servers)
        assert "Flood Data Server" in result
        assert "flood.example.com" in result
        assert "1 new OGC server" in result
