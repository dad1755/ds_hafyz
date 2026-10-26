"""Evidence helper: direct pipeline vs the loaded service vs the CLI, on the six S5 inputs.

Run from the repository root inside the application image:

    python evidence/s5/compare_cli_vs_pipeline.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import joblib
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
from test_prediction import SYNTHETIC_RECORDS  # noqa: E402  (the test's own inputs)

from ml.schema import FEATURES  # noqa: E402
from src.inference import load_service  # noqa: E402

ARTIFACT = REPO / "models" / "best_pipeline.joblib"


def direct(pipeline, record: dict[str, int]) -> tuple[float, int]:
    frame = pd.DataFrame([[record[name] for name in FEATURES]], columns=list(FEATURES))
    probability = float(pipeline.predict_proba(frame)[0, 1])
    return probability, int(pipeline.predict(frame)[0])


def main() -> int:
    pipeline = joblib.load(ARTIFACT)
    service = load_service(REPO / "models")

    header = (
        f"{'input':<6}{'direct joblib (repr)':<26}{'service (repr)':<26}"
        f"{'CLI (repr)':<26}{'class d/s/c':<14}{'identical'}"
    )
    print(header)
    print("-" * len(header))
    all_identical = True
    for index, record in enumerate(SYNTHETIC_RECORDS, start=1):
        expected_probability, expected_class = direct(pipeline, record)
        result = service.predict(record)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(record, handle)
            request = handle.name
        completed = subprocess.run(
            [sys.executable, "-m", "src.inference", "--input", request, "--models-dir", "models"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            print(f"input {index}: CLI failed\n{completed.stdout}{completed.stderr}")
            return 1
        payload = json.loads(completed.stdout)

        classes = f"{expected_class}/{result.predicted_class}/{payload['predicted_class']}"
        identical = (
            repr(expected_probability) == repr(result.probability) == repr(payload["probability"])
            and expected_class == result.predicted_class == payload["predicted_class"]
        )
        all_identical = all_identical and identical
        print(
            f"{index:<6}{repr(expected_probability):<26}{repr(result.probability):<26}"
            f"{repr(payload['probability']):<26}{classes:<14}{'yes' if identical else 'NO'}"
        )

    print()
    print(f"all six inputs: class and probability byte-identical across all three paths: {all_identical}")
    return 0 if all_identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
