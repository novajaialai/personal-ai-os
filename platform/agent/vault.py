from pathlib import Path

VAULT = Path("/vault")
CONTEXT_FILES = ["about-me.md", "working-style.md", "brand-voice.md", "voc.md"]


def _read(rel: str) -> str:
    p = VAULT / "context" / rel
    return p.read_text() if p.exists() else ""


def load_context() -> dict[str, str]:
    return {f.removesuffix(".md"): _read(f) for f in CONTEXT_FILES}


def write_to_inbox(filename: str, content: str) -> Path:
    inbox = VAULT / "Inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / filename
    dest.write_text(content)
    return dest
