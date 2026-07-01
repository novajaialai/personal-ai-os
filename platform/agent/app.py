import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import anthropic
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import db
import vault
from prompts import build_system_prompt

MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "4096"))
MAX_TOOL_ROUNDS = 8

_client: anthropic.Anthropic | None = None

TOOLS = [
    {
        "name": "list_notes",
        "description": "List every markdown note in the vault (vault-relative paths).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_notes",
        "description": "Full-text search across all notes in the vault. Returns matching file paths, line numbers, and snippets.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search term or phrase"}},
            "required": ["query"],
        },
    },
    {
        "name": "read_note",
        "description": "Read the full contents of one note by its vault-relative path (e.g. 'Projects/foo.md').",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_note",
        "description": "Create a new note or overwrite an existing one at the given vault-relative path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "e.g. 'Projects/idea.md'"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "append_note",
        "description": "Append a new timestamped entry to an existing note (creating it if it doesn't exist yet). Use this for running logs / journals rather than write_note, which overwrites.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
]


def _run_tool(name: str, tool_input: dict) -> str:
    try:
        if name == "list_notes":
            return "\n".join(vault.list_notes()) or "(vault is empty)"
        if name == "search_notes":
            results = vault.search_notes(tool_input["query"])
            if not results:
                return "no matches"
            return "\n".join(f"{r['path']}:{r['line']}: {r['text']}" for r in results)
        if name == "read_note":
            return vault.read_note(tool_input["path"])
        if name == "write_note":
            path = vault.write_note(tool_input["path"], tool_input["content"])
            return f"wrote {path}"
        if name == "append_note":
            path = vault.append_note(tool_input["path"], tool_input["content"])
            return f"appended to {path}"
        return f"unknown tool: {name}"
    except (vault.VaultPathError, FileNotFoundError) as e:
        return f"error: {e}"


def _make_client() -> anthropic.Anthropic:
    """Prefer ANTHROPIC_AUTH_TOKEN (OAuth bearer) over ANTHROPIC_API_KEY."""
    auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if auth_token:
        return anthropic.Anthropic(auth_token=auth_token)
    if api_key:
        return anthropic.Anthropic(api_key=api_key)
    raise RuntimeError("Set ANTHROPIC_AUTH_TOKEN (OAuth) or ANTHROPIC_API_KEY in environment")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client
    db.init_db()
    _client = _make_client()
    yield


app = FastAPI(title="AIOS Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    mode: str = "second_brain"


class ChatResponse(BaseModel):
    session_id: str
    reply: str


_UI = Path(__file__).parent / "ui.html"
_HUB = Path(__file__).parent / "hub.html"


@app.get("/chat", response_class=HTMLResponse)
def ui():
    return _UI.read_text()


@app.get("/", response_class=HTMLResponse)
def hub():
    return _HUB.read_text()


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}


# Reachable by Docker Compose service name from inside the network — see
# platform/docker-compose.yml for the service list these correspond to.
_STATUS_TARGETS = {
    "chat": "http://127.0.0.1:3000/health",
    "nextcloud": "http://nextcloud:80/status.php",
    "crm": "http://twenty-server:3000/healthz",
    "bi": "http://metabase:3000/api/health",
    "flows": "http://n8n:5678/healthz",
}


@app.get("/api/status")
def api_status():
    out = {}
    with httpx.Client(timeout=1.5) as client:
        for name, url in _STATUS_TARGETS.items():
            try:
                r = client.get(url)
                out[name] = "up" if r.status_code < 500 else "down"
            except httpx.HTTPError:
                out[name] = "down"
    return out


def _digest_to_html(md: str) -> str:
    """Minimal markdown->HTML for digest content (headers, bold, paragraphs).
    No external deps/CDN — the digest format is simple and fully controlled."""
    import html as _html

    lines = md.splitlines()
    out = []
    for line in lines:
        line = _html.escape(line)
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        if line.startswith("# "):
            out.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{line[3:]}</h2>")
        elif line.strip() == "":
            out.append("")
        else:
            out.append(f"<p>{line}</p>")
    return "\n".join(out)


@app.get("/api/digest/latest")
def api_digest_latest():
    d = vault.latest_digest()
    if not d:
        return {"date": None, "content": "", "html": "<p>No digest yet.</p>"}
    return {"date": d["date"], "content": d["content"], "html": _digest_to_html(d["content"])}


_DIGEST_UI = Path(__file__).parent / "digest.html"


@app.get("/digest", response_class=HTMLResponse)
def digest_page():
    return _DIGEST_UI.read_text()


def _extract_text(content_blocks) -> str:
    return "".join(b.text for b in content_blocks if b.type == "text")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # Resolve or create session
    if req.session_id and db.session_exists(req.session_id):
        sid = req.session_id
    else:
        sid = db.create_session(title=req.message[:60], mode=req.mode)

    # Build message history
    history = db.get_messages(sid, limit=20)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": req.message})

    # Tool-use loop: keep going while Claude wants to call tools, up to a cap
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            resp = _client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=build_system_prompt(),
                messages=messages,
                tools=TOOLS,
            )
            if resp.stop_reason != "tool_use":
                reply = _extract_text(resp.content)
                break

            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                result = _run_tool(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )
            messages.append({"role": "user", "content": tool_results})
        else:
            reply = "(hit tool-use round limit — try a more specific request)"
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Persist (only the original user message and final text reply — not the
    # intermediate tool_use/tool_result blocks, which are re-derivable per turn)
    db.save_message(sid, "user", req.message)
    db.save_message(sid, "assistant", reply)
    db.touch_session(sid)

    # Update title after first exchange if still just a snippet
    if len(history) == 0:
        db.update_session_title(sid, req.message[:60])

    return ChatResponse(session_id=sid, reply=reply)


@app.get("/sessions")
def sessions():
    return db.list_sessions()


@app.get("/sessions/{session_id}")
def session_detail(session_id: str):
    detail = db.get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail
