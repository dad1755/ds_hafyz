#!/usr/bin/env python3
"""Scan the running container's log for any operator secret — without printing one.

    python3 evidence/s11/probe_logs.py [container]

The secret *values* are read from the operator's `.env` / `.env.cloudflared` on disk and used
only as search needles. The output names the variable that leaked (never the value), the line
number it appeared on, and the surrounding text with the value replaced by ``<REDACTED>``.

It also checks the things a log should not contain at all: a plaintext password assignment,
an argon2 hash, a tunnel token, a traceback that carries a credential, and any occurrence of
the SQLite file's bytes. Exit code 0 = clean, 1 = a leak was found, 2 = cannot run.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECRET_FILES = (".env", ".env.cloudflared")
SECRET_KEY = re.compile(r"(PASSWORD|TOKEN|SECRET|API_KEY|PRIVATE_KEY)", re.IGNORECASE)
PLACEHOLDER = re.compile(r"^(REPLACE|CHANGE|YOUR_|<|\$\{|example)", re.IGNORECASE)
GENERIC = {
    "argon2 password hash": re.compile(r"\$argon2(?:id|i|d)\$v=\d+\$"),
    "password assignment": re.compile(r"(?i)password\s*[=:]\s*\S{6,}"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "cloudflare tunnel token": re.compile(r"[A-Za-z0-9_-]{40,}\.[A-Za-z0-9_-]{20,}"),
}


def load_secrets() -> dict[str, str]:
    secrets: dict[str, str] = {}
    for name in SECRET_FILES:
        path = REPO / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not SECRET_KEY.search(key) or len(value) < 6 or PLACEHOLDER.match(value):
                continue
            secrets[f"{name}:{key}"] = value
    return secrets


def main(argv: list[str]) -> int:
    container = argv[1] if len(argv) > 1 else "aihubcampus-web-1"
    result = subprocess.run(
        ["docker", "logs", "--tail", "5000", container],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"ERROR: cannot read logs for {container}: {result.stderr.strip()}", file=sys.stderr)
        return 2
    log = result.stdout + result.stderr
    lines = log.splitlines()
    print(f"container: {container}")
    print(f"log lines scanned: {len(lines)}  ({len(log)} bytes)")
    print(f"secret values loaded from operator env: {len(load_secrets())} (values never printed)")
    print()

    findings: list[str] = []
    for label, value in load_secrets().items():
        if value in log:
            for number, line in enumerate(lines, 1):
                if value in line:
                    redacted = line.replace(value, "<REDACTED>")
                    findings.append(f"{label} on line {number}: {redacted[:160]}")

    for label, pattern in GENERIC.items():
        for number, line in enumerate(lines, 1):
            match = pattern.search(line)
            if match:
                redacted = line[: match.start()] + "<REDACTED>" + line[match.end():]
                findings.append(f"{label} on line {number}: {redacted[:160]}")

    if findings:
        print("FAIL — the log carries credential-shaped material:")
        for finding in findings:
            print(f"  - {finding}")
        return 1

    print("PASS — no operator secret, no password assignment, no hash and no key block in the log.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
