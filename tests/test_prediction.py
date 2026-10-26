"""Sprint 5 gate: the prediction service, its recommendation bands and its disclosures.

The acceptance text of S5 asks for four things, and each has a test here:

* **Direct pipeline vs the loaded service, class *and* probability, on ≥5 representative
  synthetic inputs.** :data:`SYNTHETIC_RECORDS` holds six, chosen to span the input contract
  (minimum limit and age, a maximum limit, a delinquent account, an account with a negative
  statement balance, an all-zero-amount account, and a mid-range account). Both sides are
  compared exactly — ``float ==`` and ``repr`` — not with a tolerance, and the CLI is compared
  the same way, so a value that changed on its way through the service would fail.
* **Threshold boundary tests exactly at 0.25 / 0.50 / 0.75**, plus a gaplessness sweep over
  ``[0, 1]`` and a class-threshold test at exactly 0.5.
* **The disclaimer and the model version on every result path** — every band, both classes.
* **Nothing trains at request time**, and no request can choose which artifact is loaded.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import pytest

from ml.schema import FEATURES
from ml.verify_artifact import ArtifactError
from src.inference import (
    CALIBRATION_NOTE,
    DISCLAIMER,
    InferenceService,
    PredictionResult,
    clear_service_cache,
    load_service,
)
from src.recommendations import TIER_NOTE, TIERS, TierError, tier_for
from src.validation import ValidationError

REPO = Path(__file__).resolve().parent.parent
MODELS = REPO / "models"
ARTIFACT = MODELS / "best_pipeline.joblib"
MANIFEST = MODELS / "model_manifest.json"

#: Six representative, contract-valid synthetic accounts. None of them is a real customer:
#: the values are hand-picked to sit on the documented edges of the 23-feature contract.
SYNTHETIC_RECORDS: list[dict[str, int]] = [
    {  # 1 — youngest accepted age, smallest accepted limit, never delinquent
        "LIMIT_BAL": 10_000, "SEX": 1, "EDUCATION": 3, "MARRIAGE": 2, "AGE": 18,
        "PAY_0": -1, "PAY_2": -1, "PAY_3": -1, "PAY_4": -1, "PAY_5": -1, "PAY_6": -1,
        "BILL_AMT1": 0, "BILL_AMT2": 0, "BILL_AMT3": 0, "BILL_AMT4": 0, "BILL_AMT5": 0,
        "BILL_AMT6": 0,
        "PAY_AMT1": 0, "PAY_AMT2": 0, "PAY_AMT3": 0, "PAY_AMT4": 0, "PAY_AMT5": 0, "PAY_AMT6": 0,
    },
    {  # 2 — largest accepted limit, current account, pays in full
        "LIMIT_BAL": 1_000_000, "SEX": 2, "EDUCATION": 1, "MARRIAGE": 1, "AGE": 45,
        "PAY_0": -1, "PAY_2": -1, "PAY_3": -1, "PAY_4": -1, "PAY_5": -1, "PAY_6": -1,
        "BILL_AMT1": 120_000, "BILL_AMT2": 98_000, "BILL_AMT3": 77_000, "BILL_AMT4": 66_000,
        "BILL_AMT5": 54_000, "BILL_AMT6": 40_000,
        "PAY_AMT1": 120_000, "PAY_AMT2": 98_000, "PAY_AMT3": 77_000, "PAY_AMT4": 66_000,
        "PAY_AMT5": 54_000, "PAY_AMT6": 40_000,
    },
    {  # 3 — three months in arrears with no payment at all
        "LIMIT_BAL": 20_000, "SEX": 2, "EDUCATION": 2, "MARRIAGE": 2, "AGE": 24,
        "PAY_0": 3, "PAY_2": 3, "PAY_3": 2, "PAY_4": 2, "PAY_5": 1, "PAY_6": 0,
        "BILL_AMT1": 3_913, "BILL_AMT2": 3_102, "BILL_AMT3": 689, "BILL_AMT4": 0,
        "BILL_AMT5": 0, "BILL_AMT6": 0,
        "PAY_AMT1": 0, "PAY_AMT2": 0, "PAY_AMT3": 0, "PAY_AMT4": 0, "PAY_AMT5": 0, "PAY_AMT6": 0,
    },
    {  # 4 — negative statement balances (a credit balance is legal in this dataset)
        "LIMIT_BAL": 50_000, "SEX": 1, "EDUCATION": 4, "MARRIAGE": 3, "AGE": 39,
        "PAY_0": -2, "PAY_2": -2, "PAY_3": -2, "PAY_4": -2, "PAY_5": -2, "PAY_6": -2,
        "BILL_AMT1": -1_200, "BILL_AMT2": -900, "BILL_AMT3": 0, "BILL_AMT4": 0,
        "BILL_AMT5": -15, "BILL_AMT6": 0,
        "PAY_AMT1": 0, "PAY_AMT2": 0, "PAY_AMT3": 0, "PAY_AMT4": 0, "PAY_AMT5": 0, "PAY_AMT6": 0,
    },
    {  # 5 — revolving credit on a large balance, minimum payments only
        "LIMIT_BAL": 300_000, "SEX": 2, "EDUCATION": 2, "MARRIAGE": 1, "AGE": 52,
        "PAY_0": 0, "PAY_2": 0, "PAY_3": 0, "PAY_4": 0, "PAY_5": 0, "PAY_6": 0,
        "BILL_AMT1": 285_000, "BILL_AMT2": 279_000, "BILL_AMT3": 271_000, "BILL_AMT4": 266_000,
        "BILL_AMT5": 260_000, "BILL_AMT6": 255_000,
        "PAY_AMT1": 2_000, "PAY_AMT2": 2_000, "PAY_AMT3": 2_000, "PAY_AMT4": 2_000,
        "PAY_AMT5": 2_000, "PAY_AMT6": 2_000,
    },
    {  # 6 — undocumented education/marriage codes, eight months of delay
        "LIMIT_BAL": 80_000, "SEX": 1, "EDUCATION": 6, "MARRIAGE": 0, "AGE": 67,
        "PAY_0": 8, "PAY_2": 8, "PAY_3": 7, "PAY_4": 6, "PAY_5": 5, "PAY_6": 4,
        "BILL_AMT1": 60_000, "BILL_AMT2": 58_000, "BILL_AMT3": 55_000, "BILL_AMT4": 50_000,
        "BILL_AMT5": 45_000, "BILL_AMT6": 40_000,
        "PAY_AMT1": 0, "PAY_AMT2": 0, "PAY_AMT3": 500, "PAY_AMT4": 500, "PAY_AMT5": 500,
        "PAY_AMT6": 500,
    },
]

VALID_RECORD = SYNTHETIC_RECORDS[2]


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def service() -> InferenceService:
    return load_service(MODELS)


@pytest.fixture(scope="module")
def direct_pipeline() -> Any:
    """The artifact loaded directly, with no service in between — the comparison baseline."""
    return joblib.load(ARTIFACT)


def direct_probability(pipeline: Any, record: dict[str, int]) -> float:
    frame = pd.DataFrame([[record[name] for name in FEATURES]], columns=list(FEATURES))
    return float(pipeline.predict_proba(frame)[0, 1])


class StubPipeline:
    """A pipeline that returns a chosen probability, so a cutoff can be hit exactly."""

    def __init__(self, probability: float) -> None:
        self.probability = probability
        self.fit_calls = 0

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        probability = self.probability
        return np.array([[1.0 - probability, probability]])

    def fit(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - must not be called
        self.fit_calls += 1
        raise AssertionError("the service fitted a model at request time")


def stub_service(probability: float) -> tuple[InferenceService, StubPipeline]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pipeline = StubPipeline(probability)
    return InferenceService(pipeline=pipeline, manifest=manifest, models_dir=MODELS), pipeline


# ------------------------------------------------------- direct pipeline vs the service
@pytest.mark.parametrize("record", SYNTHETIC_RECORDS, ids=[f"input-{i + 1}" for i in range(len(SYNTHETIC_RECORDS))])
def test_service_matches_the_direct_pipeline_exactly(record: dict[str, int], service: InferenceService, direct_pipeline: Any) -> None:
    expected_probability = direct_probability(direct_pipeline, record)
    expected_class = int(direct_pipeline.predict(pd.DataFrame([[record[name] for name in FEATURES]], columns=list(FEATURES)))[0])

    result = service.predict(record)

    assert result.probability == expected_probability, "the probability changed inside the service"
    assert repr(result.probability) == repr(expected_probability), "the probability is not bit-identical"
    assert result.predicted_class == expected_class, "the class differs from the direct pipeline"
    assert result.predicted_class == int(expected_probability >= service.threshold)


def test_at_least_five_distinct_inputs_are_compared() -> None:
    assert len(SYNTHETIC_RECORDS) >= 5
    assert len({tuple(sorted(record.items())) for record in SYNTHETIC_RECORDS}) == len(SYNTHETIC_RECORDS)


def test_the_cli_agrees_with_the_direct_pipeline(tmp_path: Path, direct_pipeline: Any) -> None:
    """The same comparison through the command line, byte for byte."""
    for index, record in enumerate(SYNTHETIC_RECORDS, start=1):
        request = tmp_path / f"request-{index}.json"
        request.write_text(json.dumps(record), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, "-m", "src.inference", "--input", str(request), "--models-dir", str(MODELS)],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        payload = json.loads(completed.stdout)
        expected = direct_probability(direct_pipeline, record)
        assert payload["probability"] == expected, f"input {index}: CLI probability differs"
        assert repr(payload["probability"]) == repr(expected), f"input {index}: not bit-identical"
        assert payload["predicted_class"] == int(expected >= 0.5), f"input {index}: class differs"


# --------------------------------------------------------------- threshold boundaries
@pytest.mark.parametrize(
    ("probability", "tier_key"),
    [
        (0.25, "watch"),
        (0.50, "high"),
        (0.75, "critical"),
    ],
)
def test_the_three_documented_cutoffs_belong_to_the_band_above(probability: float, tier_key: str) -> None:
    assert tier_for(probability).key == tier_key


@pytest.mark.parametrize(
    ("probability", "tier_key"),
    [
        (0.0, "low"),
        (0.2499, "low"),
        (0.25, "watch"),
        (0.4999, "watch"),
        (0.50, "high"),
        (0.7499, "high"),
        (0.75, "critical"),
        (0.9999, "critical"),
        (1.0, "critical"),
    ],
)
def test_bands_are_continuous_at_every_documented_edge(probability: float, tier_key: str) -> None:
    assert tier_for(probability).key == tier_key


def test_no_probability_falls_between_two_bands() -> None:
    """A sweep of 10,001 probabilities: exactly one band each, and no jump larger than one."""
    steps = 10_000
    previous_index = -1
    for step in range(steps + 1):
        probability = step / steps
        matches = [tier for tier in TIERS if tier.contains(probability)]
        assert len(matches) == 1, f"{probability} matched {[tier.key for tier in matches]}"
        index = TIERS.index(matches[0])
        assert index - previous_index <= 1, f"a band was skipped at {probability}"
        assert index >= previous_index, f"the bands are not monotonic at {probability}"
        previous_index = index


def test_the_top_band_includes_exactly_one() -> None:
    assert tier_for(1.0).key == "critical"
    assert TIERS[-1].upper == 1.0


@pytest.mark.parametrize("probability", [-0.0001, 1.0001, math.nan, math.inf, -math.inf, True, "0.5", None])
def test_an_impossible_probability_is_refused(probability: Any) -> None:
    with pytest.raises(TierError):
        tier_for(probability)


def test_class_threshold_is_exactly_one_half() -> None:
    """The class comes from the model's threshold, not from the bands."""
    below, _ = stub_service(0.4999999999)
    at, _ = stub_service(0.5)
    above, _ = stub_service(0.5000000001)

    assert below.predict(VALID_RECORD).predicted_class == 0
    assert at.predict(VALID_RECORD).predicted_class == 1
    assert above.predict(VALID_RECORD).predicted_class == 1
    # ... while the band boundary sits at the same place, on its own scale.
    assert below.predict(VALID_RECORD).risk_tier == "watch"
    assert at.predict(VALID_RECORD).risk_tier == "high"


# ------------------------------------------------------------------- every result path
@pytest.mark.parametrize(
    ("probability", "tier_key"),
    [(0.0, "low"), (0.2499, "low"), (0.25, "watch"), (0.4999, "watch"),
     (0.50, "high"), (0.7499, "high"), (0.75, "critical"), (1.0, "critical")],
)
def test_every_result_path_carries_the_disclosures(probability: float, tier_key: str) -> None:
    service, _ = stub_service(probability)
    result = service.predict(VALID_RECORD)
    payload = result.as_dict()

    assert payload["risk_tier"] == tier_key
    assert payload["disclaimer"] == DISCLAIMER
    assert payload["calibration_note"] == CALIBRATION_NOTE
    assert payload["tier_note"] == TIER_NOTE
    assert payload["model_version"] == service.model_version
    assert payload["artifact_sha256"] == service.artifact_sha256
    assert payload["probability_label"] == "Estimated model probability of next-month default"
    assert payload["class_label"] in ("Predicted non-default next month", "Predicted default next month")
    assert payload["class_caveat"]
    assert "uncalibrated" in payload["calibration_note"]
    # The false-negative warning states a measured number, not a hedge.
    assert "recall" in payload["false_negative_note"]
    assert "does not rule out default" in payload["false_negative_note"]
    # ... and the rendered lines carry the same content, disclaimer last.
    lines = result.display_lines()
    assert DISCLAIMER in lines
    assert any(f"Model version: {service.model_version}" == line for line in lines)


def test_both_classes_use_the_documented_wording() -> None:
    no_default, _ = stub_service(0.1)
    default, _ = stub_service(0.9)

    low = no_default.predict(VALID_RECORD)
    high = default.predict(VALID_RECORD)

    assert low.class_label == "Predicted non-default next month"
    assert low.class_caveat == "This is not a guarantee of payment."
    assert high.class_label == "Predicted default next month"
    assert high.class_caveat == "This is not a confirmed delinquency."


def test_real_service_result_is_a_frozen_record(service: InferenceService) -> None:
    result = service.predict(VALID_RECORD)
    assert isinstance(result, PredictionResult)
    with pytest.raises(Exception):
        result.probability = 0.99  # type: ignore[misc]
    assert set(result.as_dict()) == {
        "predicted_class", "class_label", "class_caveat", "probability", "probability_label",
        "risk_tier", "tier_label", "tier_advice", "tier_note", "threshold", "model_version",
        "artifact_sha256", "disclaimer", "calibration_note", "false_negative_note",
    }


# ------------------------------------------------------------ no training at request time
def test_prediction_never_fits_the_pipeline(service: InferenceService) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("fit() was called while serving a prediction")

    original = service._pipeline.fit  # noqa: SLF001 - the point is to poison the fitted pipeline
    service._pipeline.fit = refuse  # type: ignore[method-assign]
    try:
        result = service.predict(VALID_RECORD)
    finally:
        service._pipeline.fit = original  # type: ignore[method-assign]
    assert result.predicted_class in (0, 1)


def test_prediction_does_not_reload_or_reverify_the_artifact(service: InferenceService, monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the artifact was loaded again while serving a prediction")

    monkeypatch.setattr("src.inference.load_verified_pipeline", explode)
    assert service.predict(VALID_RECORD).probability >= 0.0


def test_the_service_is_loaded_once_and_reused() -> None:
    clear_service_cache()
    first = load_service(MODELS)
    second = load_service(MODELS)
    assert first is second


def test_invalid_input_never_reaches_the_model() -> None:
    service, pipeline = stub_service(0.5)
    bad = dict(VALID_RECORD, AGE=17)
    with pytest.raises(ValidationError) as error:
        service.predict(bad)
    assert error.value.code == "out_of_range"
    assert pipeline.fit_calls == 0

    missing = {name: value for name, value in VALID_RECORD.items() if name != "AGE"}
    with pytest.raises(ValidationError) as error:
        service.predict(missing)
    assert error.value.code == "missing_feature"

    with pytest.raises(ValidationError) as error:
        service.predict(dict(VALID_RECORD, ID=1))
    assert error.value.code == "unknown_feature"

    with pytest.raises(ValidationError) as error:
        service.predict(dict(VALID_RECORD, PAY_AMT1=-1))
    assert error.value.code == "out_of_range"

    with pytest.raises(ValidationError) as error:
        service.predict(dict(VALID_RECORD, AGE=41.5))
    assert error.value.code == "non_integer"

    with pytest.raises(ValidationError) as error:
        service.predict(dict(VALID_RECORD, PAY_0=12))
    assert error.value.code == "unsupported_code"


def test_a_negative_statement_balance_is_accepted(service: InferenceService) -> None:
    """Negative bills are valid in this dataset and must not be rejected as invalid input."""
    record = dict(SYNTHETIC_RECORDS[3])
    assert record["BILL_AMT1"] < 0
    result = service.predict(record)
    assert 0.0 <= result.probability <= 1.0


# ---------------------------------------------------------- no artifact chosen per request
def test_the_service_takes_no_path_from_a_request(tmp_path: Path) -> None:
    """There is no API that accepts an uploaded joblib: the artifact path is configuration."""
    (tmp_path / "uploaded.joblib").write_bytes(ARTIFACT.read_bytes())
    with pytest.raises(ArtifactError):
        load_service(tmp_path)  # a directory with no verified manifest is refused
    # The public surface takes features, not a path.
    import inspect

    signature = inspect.signature(InferenceService.predict)
    assert list(signature.parameters) == ["self", "features"]
