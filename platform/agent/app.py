import os
from contextlib import asynccontextmanager
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import db
from prompts import build_system_prompt

MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "4096"))

_client: anthropic.Anthropic | None = None


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


@app.get("/", response_class=HTMLResponse)
@app.get("/chat", response_class=HTMLResponse)
def ui():
    return _UI.read_text()


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}


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

    # Call Claude
    try:
        resp = _client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=build_system_prompt(),
            messages=messages,
        )
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=str(e))

    reply = resp.content[0].text

    # Persist
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
