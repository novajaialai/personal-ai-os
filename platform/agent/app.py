import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterator

import anthropic
import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

import db
import services
import vault
import voice
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
    {
        "name": "service_api",
        "description": (
            "Call the REST API of a business service running on this box. Services and their APIs:\n"
            "- crm: Twenty CRM. REST at /rest/<objectPlural> (people, companies, opportunities, notes, tasks). "
            "Create person: POST /rest/people with {'name':{'firstName':...,'lastName':...},'emails':{'primaryEmail':...},'phones':{'primaryPhoneNumber':...},'jobTitle':...,'city':...}. "
            "Link to company via companyId. Search: GET /rest/people?filter=name.firstName[eq]:Jane or GraphQL POST /graphql. "
            "GET /rest/people returns all people; GET /open-api/core returns the full schema if unsure.\n"
            "- metabase: Metabase API. GET /api/database lists DBs; POST /api/dataset runs a query "
            "{'database':<id>,'type':'native','native':{'query':'SELECT …'}}; /api/card for saved questions; /api/dashboard for dashboards.\n"
            "- n8n: n8n public API under /api/v1 (workflows, executions). GET /api/v1/workflows lists; "
            "POST /api/v1/workflows creates; POST /api/v1/workflows/{id}/activate activates.\n"
            "- nextcloud: OCS API under /ocs/v2.php (users, shares — append ?format=json) and WebDAV under "
            "/remote.php/dav/files/<user>/ (PROPFIND to list, PUT via body as string).\n"
            "Rules: read freely; create/update freely when the user asked for it; for DELETE or anything "
            "destructive, confirm with the user first unless they just explicitly asked for that exact deletion."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": ["crm", "metabase", "n8n", "nextcloud"]},
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "PROPFIND", "MKCOL"]},
                "path": {"type": "string", "description": "Path starting with /, e.g. /rest/people"},
                "body": {"type": "object", "description": "JSON body for POST/PUT/PATCH"},
                "params": {"type": "object", "description": "Query-string parameters"},
            },
            "required": ["service", "method", "path"],
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
        if name == "service_api":
            return services.call(
                tool_input["service"],
                tool_input["method"],
                tool_input["path"],
                body=tool_input.get("body"),
                params=tool_input.get("params"),
            )
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
_THEME = Path(__file__).parent / "theme.css"


@app.get("/chat", response_class=HTMLResponse)
def ui():
    return _UI.read_text()


@app.get("/", response_class=HTMLResponse)
def hub():
    return _HUB.read_text()


@app.get("/theme.css")
def theme_css():
    return Response(content=_THEME.read_text(), media_type="text/css")


@app.get("/api/hub-config")
def hub_config():
    """Per-tenant links for the hub's business-tool cards. Values come from the
    injected .env (platform/ stays tenant-free — locked rule #5)."""
    host = os.getenv("AIOS_HOSTNAME", "")

    def _default(port: int) -> str:
        return f"https://{host}:{port}/" if host else ""

    flows = os.getenv("N8N_HOSTNAME", "")
    if flows and not flows.startswith("http"):
        flows = "https://" + flows
    return {
        "crm": os.getenv("TWENTY_SERVER_URL") or _default(8443),
        "bi": os.getenv("METABASE_SITE_URL") or _default(8444),
        "flows": flows or _default(8445),
        "files": "/files",
    }


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}


@app.get("/api/services")
def api_services():
    """Which business services the agent can operate (keys present in .env)."""
    return services.status()


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
    # Voice isn't a service to ping — it's "up" only once both provider keys exist.
    out["voice"] = "up" if (voice.GROQ_API_KEY and voice.ELEVENLABS_API_KEY) else "down"
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


def agent_stream(
    message: str, session_id: str | None, mode: str = "second_brain"
) -> Iterator[tuple[str, str]]:
    """The one agent loop — chat (streaming + non-streaming) and voice all run
    through this. Yields events:
      ("session", sid)    — once, as soon as the session is known
      ("text", delta)     — a streamed chunk of assistant text
      ("flush", "")       — text so far was pre-tool narration; a tool round ran
      ("error", detail)   — API failure; nothing was persisted
    The reply persisted (and returned by agent_reply) is the text after the
    last flush — the final round only, matching the pre-streaming behavior."""
    if session_id and db.session_exists(session_id):
        sid = session_id
    else:
        sid = db.create_session(title=message[:60], mode=mode)
    yield ("session", sid)

    history = db.get_messages(sid, limit=20)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": message})

    reply = ""
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            with _client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=build_system_prompt(),
                messages=messages,
                tools=TOOLS,
            ) as stream:
                for delta in stream.text_stream:
                    reply += delta
                    yield ("text", delta)
                resp = stream.get_final_message()

            if resp.stop_reason != "tool_use":
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
            reply = ""
            yield ("flush", "")
        else:
            reply = "(hit tool-use round limit — try a more specific request)"
            yield ("text", reply)
    except anthropic.APIError as e:
        yield ("error", str(e))
        return

    # Persist (only the original user message and final text reply — not the
    # intermediate tool_use/tool_result blocks, which are re-derivable per turn)
    db.save_message(sid, "user", message)
    db.save_message(sid, "assistant", reply)
    db.touch_session(sid)

    if len(history) == 0:
        db.update_session_title(sid, message[:60])


def agent_reply(message: str, session_id: str | None, mode: str = "second_brain") -> tuple[str, str]:
    """Non-streaming wrapper around agent_stream. Returns (session_id, reply)."""
    sid, reply = "", ""
    for kind, data in agent_stream(message, session_id, mode):
        if kind == "session":
            sid = data
        elif kind == "text":
            reply += data
        elif kind == "flush":
            reply = ""
        elif kind == "error":
            raise HTTPException(status_code=502, detail=data)
    return sid, reply


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    sid, reply = agent_reply(req.message, req.session_id, req.mode)
    return ChatResponse(session_id=sid, reply=reply)


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE variant of /chat — events mirror agent_stream's, JSON per line."""

    def gen():
        for kind, data in agent_stream(req.message, req.session_id, req.mode):
            payload = {"type": kind}
            if kind == "session":
                payload["session_id"] = data
            elif kind == "text":
                payload["text"] = data
            elif kind == "error":
                payload["detail"] = data
            yield f"data: {json.dumps(payload)}\n\n"
        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


_VOICE_UI = Path(__file__).parent / "voice.html"
_VOICE_PICKER_UI = Path(__file__).parent / "voice-picker.html"


@app.get("/voice", response_class=HTMLResponse)
def voice_page():
    return _VOICE_UI.read_text()


@app.get("/voice-picker", response_class=HTMLResponse)
def voice_picker_page():
    return _VOICE_PICKER_UI.read_text()


@app.get("/api/voice-picker/voices")
def voice_picker_list():
    return voice.STOCK_VOICES


@app.get("/api/voice-picker/preview")
def voice_picker_preview(voice_id: str):
    try:
        audio = voice.synthesize(
            "Hey, this is your second brain. Here's how I sound with this voice.",
            voice_id=voice_id,
        )
    except voice.VoiceNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")
    return Response(content=audio, media_type="audio/mpeg")


class VoiceSelectRequest(BaseModel):
    voice_id: str


@app.post("/api/voice-picker/select")
def voice_picker_select(req: VoiceSelectRequest):
    voice.set_voice_id(req.voice_id)
    return {"status": "ok", "voice_id": req.voice_id}


@app.get("/api/voice-picker/current")
def voice_picker_current():
    return {"voice_id": voice.current_voice_id()}


@app.post("/voice")
async def voice_endpoint(
    audio: UploadFile = File(...),
    session_id: str | None = Form(None),
    mode: str = Form("second_brain"),
):
    """Push-to-talk voice loop (Phase 5): audio in -> STT -> same agent_reply()
    used by /chat -> TTS -> audio out. Same session_id continues a thread
    started by text, per the shared-memory design in runbook-phase5.md."""
    audio_bytes = await audio.read()
    try:
        text = voice.transcribe(audio_bytes, filename=audio.filename or "audio.webm")
    except voice.VoiceNotConfigured as e:
        raise HTTPException(status_code=503, detail=f"voice not configured: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"STT failed: {e}")

    sid, reply = agent_reply(text, session_id, mode)

    try:
        audio_reply = voice.synthesize(reply)
    except voice.VoiceNotConfigured as e:
        raise HTTPException(status_code=503, detail=f"voice not configured: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")

    # Header values must be ASCII/single-line — percent-encode free text (transcripts
    # and replies routinely contain newlines, emoji, smart quotes).
    from urllib.parse import quote

    return Response(
        content=audio_reply,
        media_type="audio/mpeg",
        headers={
            "X-Session-Id": sid,
            "X-Transcript": quote(text),
            "X-Reply-Text": quote(reply),
        },
    )


@app.get("/sessions")
def sessions():
    return db.list_sessions()


@app.get("/sessions/{session_id}")
def session_detail(session_id: str):
    detail = db.get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail
