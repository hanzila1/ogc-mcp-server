"""
Entry point for the OGC MCP Server.
Run with: mcp dev main.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from ogc_mcp.server import mcp

if __name__ == "__main__":
    mcp.run()