"""Authenticated HTTP access to the business services on this box.

One registry entry per service: internal base URL (Docker network names — nothing
leaves the box) plus auth taken from the tenant .env. The agent gets ONE generic
tool (service_api in app.py) instead of dozens of narrow wrappers; the model
already knows these products' REST APIs.

A service with no key configured stays visible but returns a clear
"not configured" message naming the .env variable to set.
"""

import json
import os

import httpx

TIMEOUT = 20.0
MAX_RESPONSE_CHARS = 12_000  # keep tool results model-sized


def _services() -> dict:
    """Read env at call time so a restart isn't needed mid-container for tests."""
    return {
        "crm": {
            "base": "http://twenty-server:3000",
            "headers": lambda: {"Authorization": f"Bearer {os.getenv('TWENTY_API_KEY', '')}"},
            "key_var": "TWENTY_API_KEY",
            "configured": lambda: bool(os.getenv("TWENTY_API_KEY")),
        },
        "metabase": {
            "base": "http://metabase:3000",
            "headers": lambda: {"X-API-KEY": os.getenv("METABASE_API_KEY", "")},
            "key_var": "METABASE_API_KEY",
            "configured": lambda: bool(os.getenv("METABASE_API_KEY")),
        },
        "n8n": {
            "base": "http://n8n:5678",
            "headers": lambda: {"X-N8N-API-KEY": os.getenv("N8N_API_KEY", "")},
            "key_var": "N8N_API_KEY",
            "configured": lambda: bool(os.getenv("N8N_API_KEY")),
        },
        "nextcloud": {
            "base": "http://nextcloud:80",
            # OCS + WebDAV both accept basic auth with an app password.
            "headers": lambda: {"OCS-APIRequest": "true"},
            "auth": lambda: (
                os.getenv("NEXTCLOUD_USER", ""),
                os.getenv("NEXTCLOUD_APP_PASSWORD", ""),
            ),
            "key_var": "NEXTCLOUD_USER + NEXTCLOUD_APP_PASSWORD",
            "configured": lambda: bool(
                os.getenv("NEXTCLOUD_USER") and os.getenv("NEXTCLOUD_APP_PASSWORD")
            ),
        },
    }


def status() -> dict:
    return {name: ("configured" if s["configured"]() else f"missing {s['key_var']} in .env")
            for name, s in _services().items()}


def call(service: str, method: str, path: str, body: dict | None = None,
         params: dict | None = None) -> str:
    services = _services()
    if service not in services:
        return f"error: unknown service '{service}'. Available: {', '.join(services)}"
    s = services[service]
    if not s["configured"]():
        return (f"error: {service} is not configured yet — the owner must add "
                f"{s['key_var']} to the server .env and restart the agent.")

    method = method.upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "PROPFIND", "MKCOL"):
        return f"error: unsupported method {method}"
    if not path.startswith("/"):
        path = "/" + path

    try:
        kwargs: dict = {
            "headers": s["headers"](),
            "params": params or None,
            "timeout": TIMEOUT,
        }
        if "auth" in s:
            kwargs["auth"] = s["auth"]()
        if body is not None:
            kwargs["json"] = body
        r = httpx.request(method, s["base"] + path, **kwargs)
    except httpx.HTTPError as e:
        return f"error: request to {service} failed: {e}"

    text = r.text
    try:  # compact JSON responses so more fits in the budget
        text = json.dumps(r.json(), separators=(",", ":"), ensure_ascii=False)
    except ValueError:
        pass
    if len(text) > MAX_RESPONSE_CHARS:
        text = text[:MAX_RESPONSE_CHARS] + f"\n…(truncated, {len(text)} chars total)"
    return f"HTTP {r.status_code}\n{text}"
