"""Read-only inference service (blueprint §5 steps 7–10; §9 SPRINT 5).

The one supported way to score a request in this application. It:

* **verifies before it loads.** :func:`load_service` runs :func:`ml.verify_artifact.verify_models_dir`
  first and raises :class:`ml.verify_artifact.ArtifactError` if any check fails, so a
  modified, truncated or foreign artifact is never deserialised by the app.
* **loads once, read-only.** The pipeline is loaded through a process-wide cache keyed by the
  resolved models directory and is never written back. Nothing is fitted, refitted or
  updated at request time — :meth:`InferenceService.predict` only calls ``predict_proba``
  on the already-fitted pipeline.
* **predicts from the manifest's feature order.** The request is validated by
  :func:`src.validation.validate_features` (the S2 contract: every one of the 23 features,
  whole numbers, legal code sets, documented ranges) and then assembled into a one-row frame
  in exactly ``manifest["features"]["order"]``, which verification has already proven equal
  to ``ml.schema.FEATURES``.
* **never loads an uploaded file.** No public entry point accepts a path from a request: the
  artifact is always ``<models_dir>/best_pipeline.joblib``, and ``models_dir`` comes from the
  process configuration, never from user input. There is deliberately no ``predict_from_file``.
* **always returns the same disclosure.** Every :class:`PredictionResult` carries the class
  label with its caveat, the probability label, the risk band with its non-regulatory note,
  the uncalibrated-probability note, the model's measured false-negative rate and the
  disclaimer. There is no result path that omits them.

Wording is blueprint §5 step 9 verbatim: class 0 is *"Predicted non-default next month"*
(not a guarantee of payment), class 1 is *"Predicted default next month"* (not a confirmed
delinquency), and the number is the *"Estimated model probability of next-month default"*.

Usage (the CLI exists so a test can prove the loaded service and a direct pipeline call
produce the same class and the same probability):
    python -m src.inference --input request.json --models-dir models
    echo '{"LIMIT_BAL": 20000, ...}' | python -m src.inference --input -
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ml.schema import FEATURES
from ml.verify_artifact import ArtifactError, load_verified_pipeline
from src.recommendations import TIER_NOTE, RiskTier, tier_for
from src.validation import ValidationError, validate_features

#: Default artifact location: ``<repository root>/models``. The container image ships the
#: same two files at ``/app/models``, and ``Path(__file__).parent.parent`` resolves there too.
DEFAULT_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

DISCLAIMER = (
    "Academic decision-support demonstration built on the public 2005 Taiwanese credit-card "
    "dataset. It is not financial advice, not a credit decision and not an automated "
    "sanction: no limit is frozen, no application is rejected and nothing is reported about "
    "a person without a human decision. Do not enter real customer data."
)

CALIBRATION_NOTE = (
    "The probability is uncalibrated — no calibration test has been run — so read it as the "
    "model's own score, not as a real-world risk percentage."
)


class InferenceError(RuntimeError):
    """The service cannot produce a result. The message names the problem, never a value."""


@dataclass(frozen=True)
class PredictionResult:
    """One scored request, with every disclosure the result screen must show.

    Frozen because a result is a record: once returned it is what was shown, and it is what
    the user's prediction history will store in S7.
    """

    predicted_class: int
    class_label: str
    class_caveat: str
    probability: float
    probability_label: str
    risk_tier: str
    tier_label: str
    tier_advice: str
    tier_note: str
    threshold: float
    model_version: str
    artifact_sha256: str
    disclaimer: str
    calibration_note: str
    false_negative_note: str

    def as_dict(self) -> dict[str, Any]:
        """The full record. Every key is present on every result — nothing is conditional."""
        return {
            "predicted_class": self.predicted_class,
            "class_label": self.class_label,
            "class_caveat": self.class_caveat,
            "probability": self.probability,
            "probability_label": self.probability_label,
            "risk_tier": self.risk_tier,
            "tier_label": self.tier_label,
            "tier_advice": self.tier_advice,
            "tier_note": self.tier_note,
            "threshold": self.threshold,
            "model_version": self.model_version,
            "artifact_sha256": self.artifact_sha256,
            "disclaimer": self.disclaimer,
            "calibration_note": self.calibration_note,
            "false_negative_note": self.false_negative_note,
        }

    def display_lines(self) -> list[str]:
        """The same content as ordered lines, ready for a result panel."""
        return [
            self.class_label,
            self.class_caveat,
            f"{self.probability_label}: {self.probability:.2%}",
            f"Risk band: {self.tier_label} — {self.tier_advice}",
            self.tier_note,
            self.calibration_note,
            self.false_negative_note,
            f"Model version: {self.model_version}",
            self.disclaimer,
        ]


class InferenceService:
    """A verified, already-fitted pipeline plus the contract it must be called with."""

    def __init__(self, *, pipeline: Any, manifest: Mapping[str, Any], models_dir: Path | str) -> None:
        features = manifest.get("features") or {}
        order = list(features.get("order") or [])
        if order != list(FEATURES):
            raise ArtifactError(
                "the manifest's feature order does not match ml.schema.FEATURES; the artifact "
                "cannot be used to score a request"
            )
        model = manifest.get("model") or {}
        threshold = model.get("threshold")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            raise ArtifactError("the manifest records no numeric decision threshold")
        version = model.get("version")
        if not isinstance(version, str) or not version.strip():
            raise ArtifactError("the manifest records no model version")
        classes = manifest.get("classes") or {}
        caveats = manifest.get("class_caveats") or {}
        if set(classes) != {"0", "1"} or set(caveats) != {"0", "1"}:
            raise ArtifactError("the manifest does not describe both classes with their caveats")
        label = manifest.get("probability_label")
        if not isinstance(label, str) or not label.strip():
            raise ArtifactError("the manifest records no probability label")
        if not hasattr(pipeline, "predict_proba"):
            raise ArtifactError("the loaded object cannot report probabilities")

        self._pipeline = pipeline
        self._manifest = dict(manifest)
        self.models_dir = Path(models_dir)
        self._order: tuple[str, ...] = tuple(order)
        self._threshold = float(threshold)
        self._version = version
        self._classes = {key: str(classes[key]) for key in ("0", "1")}
        self._caveats = {key: str(caveats[key]) for key in ("0", "1")}
        self._probability_label = label
        self._sha256 = str((manifest.get("artifact") or {}).get("sha256") or "")
        self._false_negative_note = self._build_false_negative_note()

    # ------------------------------------------------------------------ contract
    @property
    def feature_order(self) -> tuple[str, ...]:
        return self._order

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def model_version(self) -> str:
        return self._version

    @property
    def artifact_sha256(self) -> str:
        return self._sha256

    @property
    def manifest(self) -> Mapping[str, Any]:
        """A copy of the manifest this service was verified against (read-only)."""
        return dict(self._manifest)

    # ------------------------------------------------------------------ scoring
    def predict(self, features: Mapping[str, Any]) -> PredictionResult:
        """Score one 23-feature request.

        Raises :class:`src.validation.ValidationError` before the model is touched when the
        request is invalid — an invalid request never reaches ``predict_proba``.
        """
        validated = validate_features(features)
        frame = pd.DataFrame(
            [[validated[name] for name in self._order]],
            columns=list(self._order),
            dtype="int64",
        )
        probabilities = self._pipeline.predict_proba(frame)
        if getattr(probabilities, "shape", None) != (1, 2):
            raise InferenceError("the pipeline did not return one probability pair")
        probability = float(probabilities[0, 1])
        if not 0.0 <= probability <= 1.0:
            raise InferenceError("the pipeline returned a probability outside [0, 1]")
        predicted_class = 1 if probability >= self._threshold else 0
        return self._result(predicted_class, probability, tier_for(probability))

    def _result(self, predicted_class: int, probability: float, tier: RiskTier) -> PredictionResult:
        key = str(predicted_class)
        return PredictionResult(
            predicted_class=predicted_class,
            class_label=self._classes[key],
            class_caveat=self._caveats[key],
            probability=probability,
            probability_label=self._probability_label,
            risk_tier=tier.key,
            tier_label=tier.label,
            tier_advice=tier.advice,
            tier_note=TIER_NOTE,
            threshold=self._threshold,
            model_version=self._version,
            artifact_sha256=self._sha256,
            disclaimer=DISCLAIMER,
            calibration_note=CALIBRATION_NOTE,
            false_negative_note=self._false_negative_note,
        )

    def _build_false_negative_note(self) -> str:
        """State the model's measured false-negative rate, from its own evaluation record."""
        evaluation = self._manifest.get("evaluation") or {}
        metrics = evaluation.get("metrics") or {}
        recall = metrics.get("recall")
        positives = (evaluation.get("test_class_counts") or {}).get("1")
        rows = evaluation.get("test_rows")
        if not isinstance(recall, (int, float)) or isinstance(recall, bool):
            return (
                "This model misses a substantial share of the accounts that actually default; "
                "a non-default prediction does not rule out default."
            )
        missed = 1.0 - float(recall)
        if isinstance(positives, int) and isinstance(rows, int):
            return (
                f"False negatives are real: on the {rows:,} held-out test accounts the model "
                f"missed {missed:.1%} of the {positives:,} that actually defaulted (recall "
                f"{float(recall):.2f} at threshold {self._threshold:.2f}). A non-default "
                "prediction therefore does not rule out default."
            )
        return (
            f"False negatives are real: the model's measured recall on defaulters is "
            f"{float(recall):.2f} at threshold {self._threshold:.2f}, so a non-default "
            "prediction does not rule out default."
        )


@lru_cache(maxsize=8)
def _cached_service(resolved_models_dir: str) -> InferenceService:
    """Verify and load once per models directory, for the life of the process."""
    directory = Path(resolved_models_dir)
    pipeline, manifest = load_verified_pipeline(directory)
    return InferenceService(pipeline=pipeline, manifest=manifest, models_dir=directory)


def load_service(models_dir: Path | str | None = None) -> InferenceService:
    """Return the process-wide verified service for ``models_dir``.

    The first call verifies the artifact and loads it; later calls reuse the same object.
    ``models_dir`` is process configuration — never a value taken from a request.
    """
    directory = Path(models_dir) if models_dir is not None else DEFAULT_MODELS_DIR
    return _cached_service(str(directory.resolve()))


def clear_service_cache() -> None:
    """Drop the cached service (used by tests and after an artifact is regenerated)."""
    _cached_service.cache_clear()


# --------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score one 23-feature request with the verified pipeline and print the result."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="path to a JSON object of the 23 features, or - to read one from stdin",
    )
    parser.add_argument("--models-dir", default=None, type=Path)
    args = parser.parse_args(argv)

    try:
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    except OSError as error:
        print(f"ERROR: cannot read the request: {error}", file=sys.stderr)
        return 2
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as error:
        print(f"ERROR: the request is not valid JSON: {error}", file=sys.stderr)
        return 2

    try:
        result = load_service(args.models_dir).predict(record)
    except ValidationError as error:
        print(json.dumps({"error": error.as_dict()}, indent=2, sort_keys=True))
        return 2
    except ArtifactError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 3

    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
