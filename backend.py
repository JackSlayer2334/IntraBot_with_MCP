import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastmcp import Client as MCPClient
import ollama
from db_adapter import get_db

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8080/mcp")
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

ollama_client = ollama.Client(host=OLLAMA_BASE_URL)

CACHED_GROQ_MODEL: Optional[str] = None

def get_available_groq_model(api_key: str) -> str:
    """Dynamically discover which models are active and accessible with this Groq key."""
    global CACHED_GROQ_MODEL
    if CACHED_GROQ_MODEL:
        return CACHED_GROQ_MODEL

    try:
        import requests
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            model_ids = [m.get("id") for m in data if m.get("id") and "whisper" not in m.get("id", "").lower()]
            # Look for top models in order of preference
            for pref in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama-3.2-3b-preview", "mixtral-8x7b-32768"]:
                if pref in model_ids:
                    CACHED_GROQ_MODEL = pref
                    return pref
            if model_ids:
                CACHED_GROQ_MODEL = model_ids[0]
                return CACHED_GROQ_MODEL
    except Exception as e:
        print(f"[Groq Model Discovery Notice] {e}")

    # Fallback to standard active model
    return "llama-3.3-70b-versatile"


def call_llm_chat(messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
    """Unified LLM caller supporting both free cloud Groq API and local Ollama."""
    api_key = (GROQ_API_KEY or "").strip().strip('"').strip("'")
    if api_key:
        import requests
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        active_model = get_available_groq_model(api_key)

        models_to_try = list(dict.fromkeys([
            active_model,
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
        ]))

        last_err = ""
        for model_name in models_to_try:
            if not model_name:
                continue
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
            }
            try:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=25,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()

                err_msg = resp.text
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("error", {}).get("message", resp.text)
                except Exception:
                    pass
                last_err = f"HTTP {resp.status_code} ({model_name}): {err_msg}"
            except Exception as ex:
                last_err = str(ex)

        raise Exception(f"Groq API Error: {last_err}")

    resp = ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=messages,
        stream=False,
        options={"temperature": temperature},
    )
    return resp.get("message", {}).get("content", "").strip()


app = FastAPI(title="IntraBot Enterprise API", version="2.0.0")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auto-seed database on startup (critical for cloud deploys where app.db doesn't exist)
@app.on_event("startup")
async def startup_event():
    try:
        db = get_db()
        db.init_db()
        print("[INTRABOT] Database initialized and seeded successfully.")
    except Exception as e:
        print(f"[INTRABOT] DB startup warning: {e}")

# In-memory cache for dynamically discovered tools
CACHED_MCP_TOOLS: List[Dict[str, Any]] = []
CACHED_TOOLS_SUMMARY: List[Dict[str, str]] = []


# ---------------------------------------------------------
# Dynamic MCP Tool Discovery
# ---------------------------------------------------------
async def discover_mcp_tools(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Dynamically discover available tools from the running FastMCP server."""
    global CACHED_MCP_TOOLS, CACHED_TOOLS_SUMMARY
    if CACHED_MCP_TOOLS and not force_refresh:
        return CACHED_MCP_TOOLS

    try:
        async with MCPClient(MCP_SERVER_URL) as mcp:
            tools_list = await mcp.list_tools()
            tools = []
            summaries = []
            for tool in tools_list:
                schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}
                tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": schema,
                })
                summaries.append({
                    "name": tool.name,
                    "description": tool.description or "",
                })
            CACHED_MCP_TOOLS = tools
            CACHED_TOOLS_SUMMARY = summaries
            return tools
    except Exception as e:
        print(f"[Warning] Failed to dynamically discover MCP tools: {e}")
        return CACHED_MCP_TOOLS


async def execute_mcp_tool(tool_name: str, arguments: dict) -> Any:
    """Execute a selected tool call on the FastMCP server."""
    async with MCPClient(MCP_SERVER_URL) as mcp:
        return await mcp.call_tool(tool_name, arguments)


def normalize_tool_result(result: Any) -> Any:
    """Normalize various FastMCP result structures to python dicts or strings."""
    if hasattr(result, "data") and result.data is not None:
        return result.data
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return result.structured_content
    if hasattr(result, "content"):
        content_items = result.content
        text_items = [
            item.text if hasattr(item, "text") else str(item)
            for item in content_items
        ]
        text = "\n".join(text_items)
        try:
            return json.loads(text)
        except Exception:
            return text
    return result


# ---------------------------------------------------------
# Stage 1: Expose Tools & Decide Tool Call
# ---------------------------------------------------------
def fallback_heuristic_tool_matching(message: str) -> Optional[Tuple[str, dict]]:
    """Safe fallback matching in case the LLM is unreachable or returns non-JSON."""
    lower = message.strip().lower()

    if any(w in lower for w in ["weather", "temperature", "forecast", "temp"]):
        match = re.search(r"\b(?:in|at|for)\s+([a-zA-Z\s]+)", message, re.IGNORECASE)
        if match:
            city = re.sub(r"\b(today|now|currently|current|weather|temperature|temp|please)\b", "", match.group(1), flags=re.IGNORECASE)
            city = re.sub(r"[^a-zA-Z\s]", "", city).strip().title()
            if city:
                return "get_weather", {"city": city}

    # Policy queries
    policy_keywords = {
        "leave": "Leave Policy",
        "vacation": "Leave Policy",
        "wfh": "WFH Policy",
        "work from home": "WFH Policy",
        "remote": "WFH Policy",
        "medical": "Medical Policy",
        "insurance": "Medical Policy",
        "health": "Medical Policy",
        "travel": "Travel Policy",
        "parental": "Parental Leave Policy",
        "maternity": "Parental Leave Policy",
        "paternity": "Parental Leave Policy",
        "learning": "Learning & Development Policy",
        "development": "Learning & Development Policy",
        "certification": "Learning & Development Policy",
        "equipment": "Equipment Policy",
        "laptop": "Equipment Policy",
        "macbook": "Equipment Policy",
        "monitor": "Equipment Policy",
    }
    for kw, pol_name in policy_keywords.items():
        if kw in lower and ("policy" in lower or kw in ["wfh", "work from home", "insurance", "laptop", "macbook", "equipment"]):
            return "get_policy", {"policy_name": pol_name}

    if any(k in lower for k in ["list employees", "all employees", "who works", "show employees", "directory", "team members"]):
        return "list_employees", {}

    # Department queries
    dept_map = {
        "engineering": "Engineering",
        "hr": "HR",
        "human resources": "HR",
        "it": "IT",
        "information technology": "IT",
        "marketing": "Marketing",
        "finance": "Finance",
        "design": "Design",
        "ui/ux": "Design",
        "sales": "Sales",
        "product": "Product",
    }
    for dept_key, dept_name in dept_map.items():
        if dept_key in lower and any(w in lower for w in ["contact", "email", "lead", "department", "head of"]):
            return "get_department_contact", {"department": dept_name}

    # Employee specific queries
    known_names = [
        "suresh", "rahul", "priya", "arjun", "ayush",
        "neha", "rohan", "ananya", "vikram", "tanya", "rohit", "sneha"
    ]
    detected_name = None
    for name in known_names:
        if re.search(rf"\b{re.escape(name)}\b", lower):
            detected_name = name.title()
            break

    if not detected_name:
        match = re.search(r"\b(?:for|of|is)\s+([a-zA-Z]+)", lower)
        if match:
            candidate = match.group(1).title()
            if candidate.lower() not in {"the", "a", "an", "our", "company", "current", "your", "my", "our", "team"}:
                detected_name = candidate

    if detected_name:
        if "leave" in lower or "balance" in lower:
            return "get_employee_leave_status", {"name": detected_name}
        if any(w in lower for w in ["manager", "approver", "reporting", "reports to"]):
            return "get_approver", {"name": detected_name}
        if any(w in lower for w in ["status", "available", "availability"]):
            return "get_employee_status", {"name": detected_name}

    return None


async def stage_1_decide_tool(user_message: str, tools: List[Dict[str, Any]]) -> Optional[Tuple[str, dict]]:
    """
    Stage 1: Expose dynamically discovered MCP tools to the LLM to decide
    whether a tool call is required and extract function arguments.
    """
    tools_spec = []
    for t in tools:
        tools_spec.append({
            "name": t["name"],
            "description": t["description"],
            "parameters": t.get("parameters", {}),
        })

    system_prompt = (
        "You are the IntraBot Tool Router. Your job is to select the single best tool to answer the user's inquiry, or determine if no tool is needed.\n"
        "Here is the list of available enterprise tools:\n"
        f"{json.dumps(tools_spec, indent=2)}\n\n"
        "Instructions:\n"
        "1. If a tool is relevant, respond ONLY with a JSON object in this exact format:\n"
        '   {"tool": "<tool_name>", "arguments": {"<param>": "<value>"}}\n'
        "2. If NO tool is needed (e.g. greetings, casual chat, general assistance), respond ONLY with:\n"
        '   {"tool": null}\n'
        "3. Do not include any explanations, markdown code blocks, or preamble. Return ONLY raw JSON."
    )

    try:
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(
            None,
            lambda: call_llm_chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,
            )
        )

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            tool_name = data.get("tool")
            args = data.get("arguments", {})
            if tool_name and any(t["name"] == tool_name for t in tools):
                return tool_name, args
            elif tool_name is None:
                return None
    except Exception as e:
        print(f"[Stage 1] LLM tool routing fallback: {e}")

    # Fallback to heuristic pattern matching if LLM was unavailable or returned non-JSON
    return fallback_heuristic_tool_matching(user_message)


# ---------------------------------------------------------
# Stage 2: Synthesize Context-Aware Response
# ---------------------------------------------------------
async def stage_2_synthesize_response(user_message: str, tool_name: str, tool_result: Any) -> str:
    """
    Stage 2: Pass the user question and real tool execution data back
    into the LLM to synthesize a friendly, context-aware markdown response.
    """
    synthesis_prompt = (
        "You are IntraBot, an intelligent and polite enterprise AI assistant.\n"
        "A user asked a question, and you retrieved verified internal corporate/tool data.\n"
        "Synthesize a clear, helpful, professional, and context-aware markdown answer for the user.\n"
        "Include all relevant details provided by the tool. Use bullet points or bold text where appropriate.\n\n"
        f"User Query: {user_message}\n"
        f"Tool Executed: {tool_name}\n"
        f"Verified Tool Data:\n{json.dumps(tool_result, indent=2) if isinstance(tool_result, (dict, list)) else str(tool_result)}"
    )

    try:
        loop = asyncio.get_event_loop()
        reply = await loop.run_in_executor(
            None,
            lambda: call_llm_chat(
                [
                    {"role": "system", "content": "You are IntraBot, an enterprise HR and workplace copilot."},
                    {"role": "user", "content": synthesis_prompt},
                ],
                temperature=0.2,
            )
        )
        return reply
    except Exception as e:
        print(f"[Stage 2] Synthesis fallback due to: {e}")
        return format_fallback_markdown(tool_name, tool_result)


def format_fallback_markdown(tool_name: str, value: Any) -> str:
    """Clean markdown formatting fallback if synthesis is unavailable."""
    if isinstance(value, str):
        return value

    if isinstance(value, dict) and value.get("error"):
        return f"⚠️ {value['error']}"

    if tool_name == "get_employee_leave_status" and isinstance(value, dict):
        return (
            f"### Leave Status for {value['name']}\n\n"
            f"* **Role:** {value['role']}\n"
            f"* **Department:** {value['department']}\n"
            f"* **Current Status:** {value['status']}\n"
            f"* **Leave Balance:** {value['leave_balance']} days\n"
            f"* **Approver:** {value['approver']}"
        )

    if tool_name == "get_employee_status" and isinstance(value, dict):
        return f"**{value['name']}** is currently **{value['status']}**."

    if tool_name == "get_leave_balance" and isinstance(value, dict):
        return f"**{value['name']}** has **{value['leave_balance']} days** of paid leave remaining."

    if tool_name == "get_approver" and isinstance(value, dict):
        return f"**{value['employee']}**'s reporting manager is **{value['approver']}**."

    if tool_name == "get_policy" and isinstance(value, dict):
        return f"### {value['policy_name']}\n\n{value['description']}"

    if tool_name == "get_department_contact" and isinstance(value, dict):
        return (
            f"### {value['department']} Department Contact\n\n"
            f"* **Lead:** {value['contact_name']}\n"
            f"* **Email:** {value['email']}"
        )

    if tool_name == "list_employees" and isinstance(value, list):
        lines = ["### Registered Employees Directory\n"]
        for emp in value:
            lines.append(f"* **{emp['name']}** — {emp['role']} ({emp['department']}) | Status: {emp['status']} | Leave: {emp['leave_balance']} days")
        return "\n".join(lines)

    return json.dumps(value, indent=2)


# ---------------------------------------------------------
# HTTP API Endpoints
# ---------------------------------------------------------
@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")


@app.get("/api/test-llm")
def test_llm_endpoint():
    """Diagnostic endpoint to test live Groq / LLM connectivity."""
    api_key = (GROQ_API_KEY or "").strip().strip('"').strip("'")
    if not api_key:
        return {"status": "no_key", "message": "GROQ_API_KEY is not set"}
    import requests
    headers = {"Authorization": f"Bearer {api_key}", "User-Agent": "IntraBot/2.0"}
    try:
        models_resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
        models_data = models_resp.json() if models_resp.status_code == 200 else models_resp.text
    except Exception as e:
        models_data = str(e)
        models_resp = None

    try:
        chat_resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "IntraBot/2.0"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "hello"}]},
            timeout=10,
        )
        chat_data = chat_resp.json() if chat_resp.status_code == 200 else chat_resp.text
    except Exception as e:
        chat_data = str(e)
        chat_resp = None

    return {
        "key_prefix": api_key[:8] + "...",
        "key_length": len(api_key),
        "models_status": getattr(models_resp, "status_code", None),
        "models_data": models_data,
        "chat_status": getattr(chat_resp, "status_code", None),
        "chat_data": chat_data,
    }


@app.get("/api/info")
async def get_system_info():
    """Return live system details for UI status badges."""
    tools = await discover_mcp_tools()
    active_model = f"Groq ({GROQ_MODEL})" if GROQ_API_KEY else OLLAMA_MODEL
    return {
        "status": "online",
        "model": active_model,
        "ollama_url": "Groq Cloud API" if GROQ_API_KEY else OLLAMA_BASE_URL,
        "mcp_server": MCP_SERVER_URL,
        "db_backend": DB_BACKEND.upper(),
        "tools_count": len(tools),
        "tools": [t["name"] for t in tools],
    }


@app.post("/chat")
async def chat_endpoint(data: dict):
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return {"reply": "Please enter a message.", "stage": "none"}

    # 1. Dynamic Tool Discovery
    tools = await discover_mcp_tools()

    # 2. Stage 1: Expose Tools & Decide Tool Call
    decision = await stage_1_decide_tool(user_msg, tools)

    if decision:
        tool_name, arguments = decision
        try:
            # 3. Execute Tool
            raw_result = await execute_mcp_tool(tool_name, arguments)
            result_data = normalize_tool_result(raw_result)

            # 4. Stage 2: Synthesize Context-Aware Response
            synthesized_reply = await stage_2_synthesize_response(user_msg, tool_name, result_data)
            return {
                "reply": synthesized_reply,
                "tool_used": tool_name,
                "tool_args": arguments,
                "stage": "two_stage_orchestrated",
            }
        except Exception as exc:
            return {
                "reply": (
                    f"⚠️ Error executing MCP tool `{tool_name}`: {exc}\n\n"
                    "Please ensure the MCP server is running on port 8080."
                ),
                "tool_used": tool_name,
                "stage": "error",
            }

    # Direct LLM Conversation (No tool needed)
    try:
        loop = asyncio.get_event_loop()
        reply = await loop.run_in_executor(
            None,
            lambda: call_llm_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are IntraBot, an intelligent workplace assistant for company employees. "
                            "Be courteous, concise, and helpful."
                        )
                    },
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.7,
            )
        )
        return {
            "reply": reply,
            "stage": "direct_llm",
        }
    except Exception as exc:
        print(f"[Direct LLM Warning] {exc}")
        lower = user_msg.lower()
        if any(g in lower for g in ["hi", "hello", "hey", "good morning", "good evening", "greetings"]):
            return {
                "reply": (
                    "👋 **Hello! I am INTRABOT**, your enterprise workplace copilot.\n\n"
                    "I can assist you with:\n"
                    "* **Employee Status & Leaves** (e.g. *What is Rahul's leave status?*)\n"
                    "* **7 Company Policies** (e.g. *Leave, WFH, Equipment, Medical*)\n"
                    "* **Department Directory** (e.g. *Marketing, IT, Engineering contacts*)\n"
                    "* **Live Tools** (e.g. *Weather in Srinagar*)\n\n"
                    "How can I help you today?"
                ),
                "stage": "fallback_dialogue",
            }
        elif any(c in lower for c in ["help", "what can you do", "who are you", "features", "capabilities"]):
            return {
                "reply": (
                    "⚡ **INTRABOT Capabilities**:\n\n"
                    "* **Leave & Status Lookups**: Check employee availability and remaining paid leaves.\n"
                    "* **Manager Approvers**: Discover direct reporting hierarchy.\n"
                    "* **7 Corporate Policies**: Leave, WFH/Hybrid, Equipment, Parental, Medical, Travel, L&D.\n"
                    "* **Department Leads**: Email and contact info for 8 company departments.\n"
                    "* **Live External Tools**: Weather lookup and website scraping.\n\n"
                    "💡 *Try clicking any of the Quick Prompts above!*"
                ),
                "stage": "fallback_dialogue",
            }
        else:
            return {
                "reply": (
                    "I am ready to help you with internal workplace data! "
                    "You can ask about any employee's leave balance (e.g. *Rahul*, *Sneha*, *Arjun*), "
                    "company policies (*Leave Policy*, *WFH Policy*, *Equipment Policy*), or department contacts.\n\n"
                    "💡 *Tip: Try clicking any of the Quick Prompt chips above to test.*"
                ),
                "stage": "fallback_dialogue",
            }
