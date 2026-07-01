import os
import re
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

VAULT = Path("/vault")
AGENT_URL = os.getenv("AGENT_INTERNAL_URL", "http://agent:3000")
INTAKE_SHARED_SECRET = os.getenv("INTAKE_SHARED_SECRET", "")

app = FastAPI(title="AIOS Intake")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "untitled"


def _check_auth(authorization: str | None) -> None:
    if not INTAKE_SHARED_SECRET:
        return  # no secret configured yet — tailnet-only access is the guard
    expected = f"Bearer {INTAKE_SHARED_SECRET}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="bad or missing intake token")


def _notify_agent(instruction: str) -> None:
    """Fire-and-forget: ask the agent to process what was just captured.
    Capture must succeed even if this fails or times out — the raw file is
    already safely on disk before this is called."""
    try:
        httpx.post(
            f"{AGENT_URL}/chat",
            json={"message": instruction, "session_id": "intake-processor"},
            timeout=25,
        )
    except httpx.HTTPError:
        pass  # capture already succeeded; processing can happen later on request


@app.get("/health")
def health():
    return {"status": "ok"}


class TranscriptIn(BaseModel):
    source: str  # otter | tldv | recall | voicenote
    title: str
    transcript: str
    participants: list[str] = []
    started_at: str | None = None


@app.post("/intake/transcript")
def intake_transcript(body: TranscriptIn, authorization: str | None = Header(None)):
    _check_auth(authorization)

    stamp = time.strftime("%Y-%m-%d")
    note_id = f"{stamp}-{_slug(body.title)}"
    dest = VAULT / "Inbox" / "transcripts" / f"{note_id}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = (
        f"---\n"
        f"id: {note_id}\n"
        f"source: {body.source}\n"
        f"type: meeting\n"
        f"title: {body.title}\n"
        f"started_at: {body.started_at or ''}\n"
        f"participants: {body.participants}\n"
        f"status: raw\n"
        f"---\n"
    )
    dest.write_text(f"{frontmatter}\n## Transcript\n{body.transcript}\n")

    _notify_agent(
        f"A new meeting transcript just landed at Inbox/transcripts/{note_id}.md. "
        f"Read it, extract concrete action items and append them to "
        f"Inbox/action-items.md (create it if it doesn't exist). If any follow-up "
        f"email or calendar event seems warranted, draft it as a new note under "
        f"Inbox/approvals/ describing exactly what you'd send/schedule and why — "
        f"do NOT send or schedule anything, just draft it for review."
    )
    return {"status": "captured", "id": note_id, "path": str(dest.relative_to(VAULT))}


class LeadIn(BaseModel):
    name: str
    email: str
    message: str = ""
    source: str = "jacobdart.com"
    intent: str = ""  # e.g. "requested a call", "downloaded pricing", etc.


@app.post("/intake/lead")
def intake_lead(body: LeadIn, authorization: str | None = Header(None)):
    _check_auth(authorization)

    stamp = time.strftime("%Y-%m-%d")
    lead_id = f"{stamp}-{_slug(body.name)}-{uuid.uuid4().hex[:6]}"
    dest = VAULT / "Inbox" / "leads" / f"{lead_id}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = (
        f"---\n"
        f"id: {lead_id}\n"
        f"source: {body.source}\n"
        f"type: lead\n"
        f"name: {body.name}\n"
        f"email: {body.email}\n"
        f"intent: {body.intent}\n"
        f"status: new\n"
        f"captured_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"---\n"
    )
    dest.write_text(f"{frontmatter}\n## Message\n{body.message}\n")

    _notify_agent(
        f"A new lead just came in from {body.source}, captured at "
        f"Inbox/leads/{lead_id}.md — {body.name} ({body.email}), intent: "
        f"'{body.intent}'. Read it, then draft a suggested next step as a note "
        f"under Inbox/approvals/ (a follow-up email draft and/or a proposed call "
        f"time). Do NOT send anything or touch the calendar — draft only."
    )
    return {"status": "captured", "id": lead_id, "path": str(dest.relative_to(VAULT))}
