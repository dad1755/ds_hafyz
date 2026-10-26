#!/usr/bin/env python3
"""Fail if any operator secret appears in a tracked file.

Reads the secret values from the operator's local `.env` / `.env.cloudflared`
(never printing them) and searches every tracked file in the repository, including
binary artifacts such as the `.docx` drafts.

Exit codes: 0 = clean, 1 = secret found, 2 = cannot run (no git repo).

Usage:
    python3 scripts/check_no_secrets.py
    python3 scripts/check_no_secrets.py --all-files   # include untracked, non-ignored
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SECRET_FILES = [".env", ".env.cloudflared", ".env.local"]
# Values shorter than this are too generic to search for without false positives.
MIN_SECRET_LEN = 6
# Keys whose value is a real credential in the operator env.
SECRET_KEY_HINT = re.compile(r"(PASSWORD|TOKEN|SECRET|KEY)", re.IGNORECASE)
# Placeholder text that is allowed to appear in tracked files.
PLACEHOLDER = re.compile(r"^(REPLACE|CHANGE|YOUR_|<.*>|\$\{.*\}|example|placeholder)", re.IGNORECASE)

# Generic high-entropy patterns that must never be committed regardless of .env.
PATTERNS = [
    ("cloudflare-tunnel-token", re.compile(rb"[A-Za-z0-9_-]{40,}\.[A-Za-z0-9_-]{20,}")),
    ("jwt", re.compile(rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("private-key-block", re.compile(rb"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]


def load_secrets() -> dict[str, str]:
    secrets: dict[str, str] = {}
    for name in SECRET_FILES:
        path = REPO / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not SECRET_KEY_HINT.search(key) or len(value) < MIN_SECRET_LEN:
                continue
            if PLACEHOLDER.match(value):
                continue
            secrets[f"{name}:{key}"] = value
    return secrets


def candidate_files(include_untracked: bool) -> list[Path]:
    if include_untracked:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=REPO, capture_output=True, text=True, check=False,
        )
    else:
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            cwd=REPO, capture_output=True, text=True, check=False,
        )
    if result.returncode != 0:
        print("ERROR: not a git repository", file=sys.stderr)
        raise SystemExit(2)
    files = []
    for line in result.stdout.splitlines():
        path = REPO / line
        if path.is_file():
            files.append(path)
    return files


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-files", action="store_true",
                        help="also scan untracked, non-ignored files")
    args = parser.parse_args(argv)

    secrets = load_secrets()
    files = candidate_files(args.all_files)
    print(f"scanned {len(files)} file(s); {len(secrets)} secret value(s) loaded from operator env")

    findings: list[tuple[str, str]] = []  # (key label, path) -- never the value
    for path in files:
        try:
            blob = path.read_bytes()
        except OSError as exc:
            print(f"  SKIP {path.relative_to(REPO)} ({exc})")
            continue
        for label, value in secrets.items():
            if value.encode() in blob:
                findings.append((label, str(path.relative_to(REPO))))
        for label, pattern in PATTERNS:
            if pattern.search(blob):
                findings.append((label, str(path.relative_to(REPO))))

    if findings:
        print("\nFAIL — credential material found in tracked files:")
        for label, path in findings:
            print(f"  - {label} in {path}")
        print("\nRemove the value, rotate the credential, and re-run.")
        return 1

    print("\nPASS — no operator secret and no credential pattern in any tracked file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
