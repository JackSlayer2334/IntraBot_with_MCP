# ⚡ INTRABOT — Enterprise AI Workplace Copilot

> A locally-hosted, **two-stage LLM orchestrator** powered by **FastMCP dynamic tool discovery** and a decoupled **SQLite / MySQL storage layer** for enterprise HR and workplace workflows.

[![FastMCP](https://img.shields.io/badge/MCP-FastMCP_Protocol-orange?style=flat-square)](https://modelcontextprotocol.io/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama_Gemma2-black?style=flat-square)](https://ollama.com/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

---

## 🚀 Features

- **Dynamic MCP Tool Discovery** — tools exposed and discovered at runtime from FastMCP server
- **Two-Stage LLM Orchestration** — Stage 1: tool routing via LLM / Stage 2: context-aware markdown synthesis
- **Decoupled Storage Layer** — plug-and-play SQLite (local) or MySQL (cloud VM) via `DB_BACKEND` env variable
- **9 Agent-callable MCP Tools** — employee status, leave balances, policies, dept contacts, weather, and web scraping
- **Modern Enterprise Chat UI** — status pills, quick prompt chips, markdown rendering, copy-to-clipboard
- **Dual LLM Support** — local Ollama (`gemma2:2b`) or free cloud [Groq API](https://console.groq.com) (`llama-3.1-8b-instant`)

---

## 🗂️ Project Structure

```
IntraBot_with_MCP/
├── backend.py          # FastAPI app — two-stage LLM orchestration & API endpoints
├── mcp_server.py       # FastMCP server — 9 agent-callable tools
├── db_adapter.py       # Decoupled DB layer — SQLiteDatabase & MySQLDatabase
├── sample_db.py        # Database seeder — 12 employees, 7 policies, 8 departments
├── static/
│   └── index.html      # INTRABOT Enterprise Chat UI
├── docker/
│   └── start.sh        # Docker entrypoint script
├── Dockerfile          # Docker build configuration
├── docker-compose.yml  # Docker Compose for local containerized runs
└── requirements.txt    # Python dependencies
```

---

## ⚡ Quick Start (Local)

### 1. Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally with `gemma2:2b` pulled:
  ```bash
  ollama pull gemma2:2b
  ollama serve
  ```

### 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Seed the Database

```bash
python sample_db.py
```

### 4. Start the FastMCP Server (Port 8080)

```bash
python mcp_server.py
```

### 5. Start the FastAPI Backend (Port 8000)

```bash
uvicorn backend:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Open in Browser

👉 **http://localhost:8000**

---

## ☁️ Deploy Free on Render.com (with Groq LLM)

Since free cloud servers can't run a 2GB Ollama model, IntraBot automatically uses the **free Groq cloud API** when `GROQ_API_KEY` is set.

1. Get a free key from [console.groq.com](https://console.groq.com) (no credit card needed)
2. Deploy to [Render.com](https://render.com) with these settings:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `sh -c "python mcp_server.py & uvicorn backend:app --host 0.0.0.0 --port $PORT"`
3. Set environment variables:
   | Variable | Value |
   |---|---|
   | `GROQ_API_KEY` | Your free Groq key |
   | `MCP_SERVER_URL` | `http://127.0.0.1:8080/mcp` |
   | `MCP_PORT` | `8080` |

---

## 🏗️ Architecture

```
Browser UI (index.html)
    │
    ▼ POST /chat
FastAPI Backend (backend.py :8000)
    │
    ├── Dynamic Tool Discovery → FastMCP Server (:8080) ──► db_adapter.py ──► SQLite / MySQL
    │
    ├── Stage 1: LLM Tool Router (Ollama / Groq)
    │      └── Injects discovered tool schemas → LLM selects tool & args
    │
    ├── Tool Execution → FastMCP Server → db_adapter → Database
    │
    └── Stage 2: LLM Synthesizer (Ollama / Groq)
           └── User query + raw tool data → context-aware markdown reply
```

---

## 📊 Included Demo Data

### 👥 12 Employees (8 Departments)

Suresh, Rahul, Priya, Arjun, Ayush, Neha, Rohan, Ananya, Vikram, Tanya, Rohit, Sneha

### 📜 7 Company Policies

Leave Policy, WFH Policy, Medical Policy, Travel Policy, Parental Leave Policy, Learning & Development Policy, Equipment Policy

### 🏢 8 Departments

Engineering, HR, IT, Marketing, Finance, Design, Sales, Product

---

## 💬 Example Queries

```
what is Rahul leave status
list employees
tell me about equipment policy
who is marketing department contact
what is WFH policy
what is temp in srinagar today
```

---

## 🔧 Environment Variables

| Variable          | Default                     | Description                                    |
| ----------------- | --------------------------- | ---------------------------------------------- |
| `OLLAMA_MODEL`    | `gemma2:2b`                 | Local Ollama model to use                      |
| `OLLAMA_BASE_URL` | `http://localhost:11434`    | Ollama server URL                              |
| `GROQ_API_KEY`    | _(unset)_                   | Groq cloud API key (overrides Ollama when set) |
| `GROQ_MODEL`      | `llama-3.1-8b-instant`      | Groq model to use                              |
| `MCP_SERVER_URL`  | `http://127.0.0.1:8080/mcp` | FastMCP server URL                             |
| `MCP_PORT`        | `8080`                      | FastMCP server port                            |
| `DB_BACKEND`      | `sqlite`                    | Storage backend: `sqlite` or `mysql`           |
| `WEATHER_API_KEY` | _(unset)_                   | Optional OpenWeatherMap key                    |

---

## 📄 License

MIT
