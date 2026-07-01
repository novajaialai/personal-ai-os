import subprocess
import time
from pathlib import Path

VAULT = Path("/vault")
CONTEXT_FILES = ["about-me.md", "working-style.md", "brand-voice.md", "voc.md"]
EXCLUDE_DIRS = {".git", ".obsidian", ".stfolder"}


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


class VaultPathError(ValueError):
    pass


def _resolve(rel: str) -> Path:
    """Resolve a vault-relative path, refusing to escape /vault."""
    p = (VAULT / rel).resolve()
    if VAULT.resolve() not in p.parents and p != VAULT.resolve():
        raise VaultPathError(f"path escapes vault: {rel}")
    return p


def list_notes() -> list[str]:
    """All markdown notes in the vault, as vault-relative paths."""
    out = []
    for p in VAULT.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in p.relative_to(VAULT).parts):
            continue
        out.append(str(p.relative_to(VAULT)))
    return sorted(out)


def search_notes(query: str, max_results: int = 30) -> list[dict]:
    """Grep-based search across the vault. Returns [{path, line, text}, ...]."""
    try:
        proc = subprocess.run(
            ["grep", "-rin", "--include=*.md", query, str(VAULT)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return []
    results = []
    for line in proc.stdout.splitlines():
        # format: /vault/path/to/note.md:123:matching text
        try:
            path, lineno, text = line.split(":", 2)
        except ValueError:
            continue
        rel = str(Path(path).relative_to(VAULT))
        if any(part in EXCLUDE_DIRS for part in Path(rel).parts):
            continue
        results.append({"path": rel, "line": int(lineno), "text": text.strip()})
        if len(results) >= max_results:
            break
    return results


def read_note(rel_path: str) -> str:
    p = _resolve(rel_path)
    if not p.exists():
        raise FileNotFoundError(f"no such note: {rel_path}")
    return p.read_text()


def write_note(rel_path: str, content: str) -> str:
    """Create or overwrite a note. Returns the vault-relative path written."""
    p = _resolve(rel_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return str(p.relative_to(VAULT))


def append_note(rel_path: str, content: str) -> str:
    """Append a timestamped entry to a note, creating it if needed."""
    p = _resolve(rel_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    entry = f"\n\n## {stamp}\n{content}\n"
    with p.open("a") as f:
        f.write(entry)
    return str(p.relative_to(VAULT))
