FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker/start.sh

ENV OLLAMA_MODEL=gemma2:2b \
    OLLAMA_BASE_URL=http://localhost:11434 \
    OLLAMA_ENABLE_TOOLS=false \
    MCP_SERVER_URL=http://127.0.0.1:8080/mcp \
    MCP_PORT=8080

EXPOSE 8000 8080

CMD ["./docker/start.sh"]
