"""Evidence helper: show the gate refusing four untrustworthy artifacts, in a real CLI run.

Every case is a copy of the shipped `models/` with exactly one thing changed, so the failure
is attributable. Run from the repository root inside the application image:

    python evidence/s5/tamper_demo.py
"""

from __future__ import annotations

import hashlib
import json
import pickle
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODELS = REPO / "models"
FILES = ("best_pipeline.joblib", "model_manifest.json", "metrics.json")


def copy_models(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(MODELS / name, destination / name)
    return destination


def verify(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ml.verify_artifact", "--models-dir", str(directory)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


def show(title: str, directory: Path) -> None:
    completed = verify(directory)
    print(f"# {title}")
    print(f"$ python -m ml.verify_artifact --models-dir {directory.name}")
    for line in completed.stdout.splitlines():
        if "FAIL" in line or line.startswith("RESULT") or line.strip().startswith("-"):
            print(line)
    print(f"exit={completed.returncode}")
    print()


def main() -> int:
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)

        # (a) one flipped byte in the artifact
        case = copy_models(root / "a-flipped-byte")
        payload = bytearray((case / "best_pipeline.joblib").read_bytes())
        payload[-1] ^= 0xFF
        (case / "best_pipeline.joblib").write_bytes(bytes(payload))
        show("(a) one byte of the artifact changed", case)

        # (b) a manifest that reorders the features
        case = copy_models(root / "b-reordered-features")
        manifest = json.loads((case / "model_manifest.json").read_text(encoding="utf-8"))
        manifest["features"]["order"] = list(reversed(manifest["features"]["order"]))
        (case / "model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        show("(b) the manifest reorders the 23 features", case)

        # (c) a moved decision threshold
        case = copy_models(root / "c-moved-threshold")
        manifest = json.loads((case / "model_manifest.json").read_text(encoding="utf-8"))
        manifest["model"]["threshold"] = 0.7
        (case / "model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        show("(c) the manifest moves the threshold from 0.5 to 0.7", case)

        # (d) a hostile pickle, with the manifest's checksum rewritten to match it
        case = copy_models(root / "d-hostile-pickle")
        marker = case / "executed.txt"

        class Bomb:
            """If this were ever unpickled it would write ``marker``; the allowlist stops it."""

            def __reduce__(self):
                return (marker.write_text, ("the artifact was executed",))

        hostile = pickle.dumps(Bomb())
        (case / "best_pipeline.joblib").write_bytes(hostile)
        manifest = json.loads((case / "model_manifest.json").read_text(encoding="utf-8"))
        manifest["artifact"]["sha256"] = hashlib.sha256(hostile).hexdigest()
        manifest["artifact"]["bytes"] = len(hostile)
        (case / "model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        show("(d) a hostile pickle whose checksum the manifest was rewritten to accept", case)
        print(
            "# the pickle's payload would have written executed.txt beside it; the file does "
            f"not exist: {not marker.exists()}"
        )
        print()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
