#!/bin/sh
set -eu

python mcp_server.py &
uvicorn backend:app --host 0.0.0.0 --port 8000
