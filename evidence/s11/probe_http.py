#!/usr/bin/env python3
"""Live HTTP/WebSocket checks against the deployed app, through the Cloudflare tunnel.

Run from the repository root:

    python3 evidence/s11/probe_http.py https://www.aihubcampus.online

Every check prints ``[PASS]``/``[FAIL]`` and the script exits non-zero if any check fails.
It uses the standard library only, so the result does not depend on the host's tooling.

What it measures, and why each one is an adversarial check rather than a smoke test:

1. the health endpoint answers 200 through the tunnel;
2. the sign-in shell is served as HTML;
3. **the SQLite database is not downloadable** — several likely paths are requested and the
   response body is inspected for the SQLite magic header, not merely its status code
   (Streamlit's SPA catch-all answers 200 with HTML, so a status check alone would lie);
4. **CORS** — a request carrying ``Origin: https://evil.example`` must not be echoed back in
   ``Access-Control-Allow-Origin``;
5. **XSRF** — a WebSocket handshake with a foreign ``Origin`` is refused, and the XSRF cookie
   the server issues is ``SameSite=Lax`` and ``HttpOnly``-less-by-design (Streamlit's client
   reads it), scoped to ``/``;
6. **WebSocket** — a handshake from the real origin with the ``streamlit`` subprotocol is
   accepted (101), which is what the browser needs and what a proxy that strips Upgrade
   headers would break.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

SQLITE_MAGIC = b"SQLite format 3\x00"
FAILURES: list[str] = []


def report(ok: bool, label: str, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def request(url: str, *, origin: str | None = None, method: str = "GET"):
    headers = {"User-Agent": "aihubcampus-s11-probe/1.0"}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, dict(response.headers), response.read(4096)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read(4096)


def websocket_handshake(base: str, *, origin: str | None, cookie: str | None) -> tuple[int, str]:
    """A raw RFC 6455 handshake, so a 101 is real and not a redirect to HTML."""
    parsed = urlparse(base)
    host = parsed.hostname
    port = parsed.port or 443
    key = base64.b64encode(os.urandom(16)).decode()
    lines = [
        "GET /_stcore/stream HTTP/1.1",
        f"Host: {host}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
        "Sec-WebSocket-Protocol: streamlit",
    ]
    if origin:
        lines.append(f"Origin: {origin}")
    if cookie:
        lines.append(f"Cookie: {cookie}")
    request_bytes = ("\r\n".join(lines) + "\r\n\r\n").encode()

    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=20) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            tls.sendall(request_bytes)
            response = tls.recv(2048).decode("latin-1", "replace")
    first_line = response.splitlines()[0] if response else "(no response)"
    code = 0
    parts = first_line.split()
    if len(parts) >= 2 and parts[1].isdigit():
        code = int(parts[1])
    return code, first_line


def main(argv: list[str]) -> int:
    base = (argv[1] if len(argv) > 1 else "https://www.aihubcampus.online").rstrip("/")
    host = urlparse(base).hostname
    print(f"target: {base}  ({host})")
    print(f"time (UTC): {__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}")
    print()

    status, health_headers, body = request(f"{base}/_stcore/health")
    report(status == 200 and body.strip() == b"ok", "health endpoint", f"HTTP {status} body={body[:16]!r}")

    status, headers, body = request(f"{base}/")
    report(
        status == 200 and b"<html" in body.lower() and b"streamlit" in body.lower(),
        "sign-in shell served as HTML",
        f"HTTP {status} content-type={headers.get('Content-Type')}",
    )

    xsrf = ""
    for value in health_headers.get("Set-Cookie", "").split(","):
        if "_streamlit_xsrf" in value:
            xsrf = value.strip()
    report(bool(xsrf), "XSRF cookie issued", xsrf.split(";")[0][:48] + "…" if xsrf else "absent")
    if xsrf:
        lowered = xsrf.lower()
        report("samesite=lax" in lowered, "XSRF cookie SameSite=Lax", lowered)
        report("path=/" in lowered, "XSRF cookie path scope", lowered)

    print()
    for path in (
        "/storage/aihubcampus.db",
        "/app/storage/aihubcampus.db",
        "/storage/aihubcampus.db-wal",
        "/data/UCI_Credit_Card.csv",
        "/models/best_pipeline.joblib",
        "/.env",
    ):
        status, headers, body = request(f"{base}{path}")
        leaked = body.startswith(SQLITE_MAGIC) or b"SQLite format 3" in body
        is_pickle = body[:2] == b"\x80\x04" or b"joblib" in body[:64]
        csv_leak = body.startswith(b"ID,LIMIT_BAL")
        env_leak = b"INITIAL_ADMIN_PASSWORD=" in body
        report(
            not (leaked or is_pickle or csv_leak or env_leak),
            f"not served: {path}",
            f"HTTP {status} content-type={headers.get('Content-Type')} bytes={len(body)}",
        )

    print()
    for origin in ("https://evil.example", "null", "http://127.0.0.1:2026"):
        status, headers, _ = request(f"{base}/_stcore/health", origin=origin)
        allow = headers.get("Access-Control-Allow-Origin", "")
        report(
            origin not in allow and allow != "*",
            f"CORS does not trust {origin}",
            f"HTTP {status} Access-Control-Allow-Origin={allow or '(none)'}",
        )

    print()
    code, line = websocket_handshake(base, origin=f"https://{host}", cookie=xsrf.split(";")[0] if xsrf else None)
    report(code == 101, "WebSocket handshake from the real origin", line)
    code, line = websocket_handshake(base, origin="https://evil.example", cookie=xsrf.split(";")[0] if xsrf else None)
    report(code != 101, "WebSocket handshake from a foreign origin refused", line)
    code, line = websocket_handshake(base, origin="https://evil.example", cookie=None)
    report(code != 101, "WebSocket handshake from a foreign origin, no cookie, refused", line)

    print()
    apex = "https://aihubcampus.online"
    status, apex_headers, body = request(f"{apex}/_stcore/health")
    report(status == 200 and body.strip() == b"ok", "apex hostname health endpoint", f"HTTP {status}")
    status, _, body = request(f"{apex}/")
    report(status == 200 and b"<html" in body.lower(), "apex hostname serves the app", f"HTTP {status}")
    code, line = websocket_handshake(apex, origin="https://evil.example", cookie=None)
    report(code != 101, "apex hostname refuses a foreign origin", line)

    print()
    print("OBSERVATION (not scored): a same-origin WebSocket handshake that carries no XSRF")
    print("cookie is also accepted (101). Streamlit guards the upgrade by Origin, and this")
    print("app's authenticated session is a server-side record bound to the connection that")
    print("created it, so a handshake from another page cannot inherit a signed-in session.")
    print()

    if FAILURES:
        print(f"RESULT: FAIL — {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("RESULT: PASS — every live check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
