#!/bin/sh
set -eu

# Start FastMCP server in background
python mcp_server.py &

# Wait a moment for MCP server to be ready
sleep 2

# Start FastAPI app — uses $PORT if set (Render), otherwise 8000 (local)
exec uvicorn backend:app --host 0.0.0.0 --port "${PORT:-8000}"
