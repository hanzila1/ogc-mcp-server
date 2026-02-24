"""
Integration tests for OGCClient.
Tests run against the live demo.pygeoapi.io server.

Run: pytest tests/test_ogc_client.py -v
"""

import pytest
from src.ogc_mcp.ogc_client import (
    OGCClient, OGCCollection, OGCProcess,
    OGCCollectionNotFound, OGCProcessNotFound, OGCServerNotFound
)

BASE_URL = "https://demo.pygeoapi.io/master"


@pytest.mark.asyncio
async def test_server_info():
    async with OGCClient(BASE_URL) as client:
        info = await client.get_server_info()
        assert info.title != ""
        assert info.base_url == BASE_URL
        assert isinstance(info.capabilities, list)


@pytest.mark.asyncio
async def test_get_collections():
    async with OGCClient(BASE_URL) as client:
        collections = await client.get_collections()
        assert len(collections) > 0
        assert all(isinstance(c, OGCCollection) for c in collections)
        assert all(c.id != "" for c in collections)


@pytest.mark.asyncio
async def test_get_features_basic():
    async with OGCClient(BASE_URL) as client:
        fc = await client.get_features("lakes", limit=3)
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) <= 3


@pytest.mark.asyncio
async def test_get_features_with_bbox():
    async with OGCClient(BASE_URL) as client:
        fc = await client.get_features("lakes", bbox="-10,35,40,75", limit=5)
        assert fc["type"] == "FeatureCollection"


@pytest.mark.asyncio
async def test_collection_not_found():
    async with OGCClient(BASE_URL) as client:
        with pytest.raises(OGCCollectionNotFound):
            await client.get_collection("nonexistent_xyz_123")


@pytest.mark.asyncio
async def test_get_processes():
    async with OGCClient(BASE_URL) as client:
        processes = await client.get_processes()
        assert len(processes) > 0
        assert all(isinstance(p, OGCProcess) for p in processes)


@pytest.mark.asyncio
async def test_get_process_detail():
    async with OGCClient(BASE_URL) as client:
        process = await client.get_process("hello-world")
        assert process.id == "hello-world"
        assert "name" in process.inputs


@pytest.mark.asyncio
async def test_execute_process():
    async with OGCClient(BASE_URL) as client:
        result = await client.execute_process(
            "hello-world",
            {"name": "GSoC Test", "message": "Stage 2 complete"}
        )
        assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_process_not_found():
    async with OGCClient(BASE_URL) as client:
        with pytest.raises(OGCProcessNotFound):
            await client.get_process("nonexistent_process_xyz")


@pytest.mark.asyncio
async def test_server_not_found():
    async with OGCClient("https://this-does-not-exist-xyz-123.io") as client:
        with pytest.raises(OGCServerNotFound):
            await client.get_landing_page()