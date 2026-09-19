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
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

ollama_client = ollama.Client(host=OLLAMA_BASE_URL)

def call_llm_chat(messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
    """Unified LLM caller supporting both local Ollama and free cloud Groq API."""
    if GROQ_API_KEY:
        import requests
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": temperature,
        }
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

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
    """Safe fallback matching in case the local LLM doesn't output valid JSON."""
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
        if kw in lower and ("policy" in lower or kw in ["wfh", "work from home", "insurance"]):
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
    Stage 1: Expose dynamically discovered MCP tools to Ollama to decide
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
        response = await loop.run_in_executor(
            None,
            lambda: ollama_client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                stream=False,
                options={"temperature": 0.0},
            )
        )
        content = response.get("message", {}).get("content", "").strip()

        # Extract JSON from response
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
        print(f"[Stage 1] Ollama tool routing notice: {e}")

    # Fallback to pattern matching if LLM output was indeterminate
    return fallback_heuristic_tool_matching(user_message)


# ---------------------------------------------------------
# Stage 2: Synthesize Context-Aware Response
# ---------------------------------------------------------
async def stage_2_synthesize_response(user_message: str, tool_name: str, tool_result: Any) -> str:
    """
    Stage 2: Pass the user question and real tool execution data back
    into Ollama to synthesize a friendly, context-aware markdown response.
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
        response = await loop.run_in_executor(
            None,
            lambda: ollama_client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": "You are IntraBot, an enterprise HR and workplace copilot."},
                    {"role": "user", "content": synthesis_prompt},
                ],
                stream=False,
                options={"temperature": 0.2},
            )
        )
        return response.get("message", {}).get("content", "").strip()
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


@app.get("/api/info")
async def get_system_info():
    """Return live system details for UI status badges."""
    tools = await discover_mcp_tools()
    return {
        "status": "online",
        "model": OLLAMA_MODEL,
        "ollama_url": OLLAMA_BASE_URL,
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
        response = await loop.run_in_executor(
            None,
            lambda: ollama_client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are IntraBot, an intelligent workplace assistant for company employees. "
                            "Be courteous, concise, and helpful."
                        )
                    },
                    {"role": "user", "content": user_msg},
                ],
                stream=False,
            )
        )
        return {
            "reply": response.get("message", {}).get("content", ""),
            "stage": "direct_llm",
        }
    except Exception as exc:
        return {
            "reply": f"⚠️ Could not reach Ollama model `{OLLAMA_MODEL}`: {exc}",
            "stage": "error",
        }
