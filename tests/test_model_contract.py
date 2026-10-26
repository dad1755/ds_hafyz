"""Sprint 4 gate: the shipped artifacts agree with the contract and with each other.

These tests read the committed artifacts (`models/metrics.json`, `models/model_manifest.json`,
`models/best_pipeline.joblib`) and re-derive the reported numbers from the confusion matrices
and from a fresh rebuild of the split. They assert the four things the S4 acceptance text
names — rerun reproducibility is proven by `evidence/s4/determinism.txt`, not here:

* every confusion matrix totals the 6,000 held-out rows;
* accuracy, precision, recall and F1 are consistent with TN/FP/FN/TP;
* the manifest's feature order is `ml.schema.FEATURES` and the artifact scores such a frame;
* selection used the training rows only, and the shipped artifact is the selected candidate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from ml.schema import FEATURES, SEED_SHA256, TARGET_COLUMN
from ml.train import SEED, TEST_SIZE, make_split

REPO = Path(__file__).resolve().parent.parent
MODELS = REPO / "models"
METRICS = MODELS / "metrics.json"
MANIFEST = MODELS / "model_manifest.json"
BEST = MODELS / "best_pipeline.joblib"
CSV = REPO / "data" / "UCI_Credit_Card.csv"


@pytest.fixture(scope="module")
def metrics() -> dict:
    return json.loads(METRICS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def evaluation(metrics: dict) -> dict:
    return metrics["evaluation"]


def test_artifacts_exist() -> None:
    for path in (METRICS, MANIFEST, BEST):
        assert path.is_file(), f"missing S4 artifact: {path}"


def test_split_is_the_documented_one(metrics: dict) -> None:
    split = metrics["split"]
    assert split["random_state"] == SEED == 42
    assert split["test_size"] == TEST_SIZE == 0.2
    assert split["train_rows"] + split["test_rows"] == 30000
    assert split["test_rows"] == 6000
    assert split["features"] == list(FEATURES)
    assert split["dropped"] == ["ID", TARGET_COLUMN]


def test_dataset_identity(metrics: dict) -> None:
    assert metrics["dataset"]["sha256"] == SEED_SHA256
    assert metrics["dataset"]["class_counts"] == {"0": 23364, "1": 6636}


def test_every_matrix_totals_the_held_out_rows(evaluation: dict) -> None:
    for key, payload in evaluation["models"].items():
        matrix = payload["confusion_matrix"]
        assert matrix["total"] == 6000, key
        assert matrix["tn"] + matrix["fp"] + matrix["fn"] + matrix["tp"] == 6000, key
        assert evaluation["test_rows"] == 6000


def test_metrics_are_consistent_with_the_matrices(evaluation: dict) -> None:
    for key, payload in evaluation["models"].items():
        m = payload["metrics"]
        c = payload["confusion_matrix"]
        tn, fp, fn, tp = c["tn"], c["fp"], c["fn"], c["tp"]
        total = c["total"]
        accuracy = (tn + tp) / total
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        assert m["accuracy"] == pytest.approx(accuracy, abs=1e-6), key
        assert m["precision"] == pytest.approx(precision, abs=1e-6), key
        assert m["recall"] == pytest.approx(recall, abs=1e-6), key
        assert m["f1"] == pytest.approx(f1, abs=1e-6), key


def test_baseline_is_the_majority_class(evaluation: dict, metrics: dict) -> None:
    base = evaluation["baseline"]
    class_zero = metrics["split"]["test_class_counts"]["0"]
    assert base["confusion_matrix"]["tn"] == class_zero
    assert base["confusion_matrix"]["tp"] == 0
    assert base["metrics"]["accuracy"] == pytest.approx(class_zero / 6000, abs=1e-6)
    assert base["metrics"]["recall"] == 0.0


def test_selection_used_no_test_rows(metrics: dict) -> None:
    selection = metrics["selection"]
    assert selection["test_rows_used_for_selection"] == 0
    assert selection["selected"] in metrics["candidates"]
    for payload in metrics["candidates"].values():
        assert payload["cv"]["scored_on"] == "training rows only"
        assert payload["cv"]["rows"] == metrics["split"]["train_rows"]


def test_selected_candidate_has_the_best_cv_f1(metrics: dict) -> None:
    cvs = {key: payload["cv"]["metrics"]["f1"]["mean"] for key, payload in metrics["candidates"].items()}
    best = max(cvs.values())
    assert best - cvs[metrics["selection"]["selected"]] <= 0.005


def test_manifest_matches_the_schema(manifest: dict, metrics: dict) -> None:
    assert manifest["features"]["order"] == list(FEATURES)
    assert manifest["features"]["count"] == 23
    assert manifest["model"]["threshold"] == 0.5
    assert manifest["model"]["selected"] == metrics["selection"]["selected"]
    assert manifest["model"]["positive_class"] == 1


def test_manifest_checksum_is_the_shipped_artifact(manifest: dict) -> None:
    digest = hashlib.sha256(BEST.read_bytes()).hexdigest()
    assert manifest["artifact"]["sha256"] == digest
    assert manifest["artifact"]["bytes"] == BEST.stat().st_size


def test_loaded_pipeline_scores_a_contract_frame(manifest: dict) -> None:
    pipeline = joblib.load(BEST)
    frame = pd.DataFrame([{name: 1 for name in FEATURES}], columns=list(FEATURES))
    prediction = pipeline.predict(frame)
    probabilities = pipeline.predict_proba(frame)
    assert prediction.shape == (1,)
    assert int(prediction[0]) in (0, 1)
    assert probabilities.shape == (1, 2)
    assert probabilities.sum() == pytest.approx(1.0, abs=1e-9)
    assert 0.0 <= float(probabilities[0, 1]) <= 1.0

    # The transform selects columns by name, so a reordered frame is the same frame ...
    reordered = frame[list(FEATURES)[::-1]]
    assert np.array_equal(pipeline.predict(reordered), prediction)
    # ... and a frame that is missing a contract column is rejected rather than guessed at.
    with pytest.raises((KeyError, ValueError)):
        pipeline.predict(frame.drop(columns=[FEATURES[0]]))


def test_rebuilt_split_reproduces_the_recorded_counts(metrics: dict) -> None:
    frame = pd.read_csv(CSV, usecols=list(FEATURES) + [TARGET_COLUMN])
    record = make_split(frame)["record"]
    for side in ("train_rows", "test_rows", "train_class_counts", "test_class_counts"):
        assert record[side] == metrics["split"][side], side


def test_shipped_pipeline_reproduces_its_candidate(evaluation: dict) -> None:
    selected = evaluation["selected"]
    candidate = joblib.load(MODELS / "candidates" / f"{selected}.joblib")
    best = joblib.load(BEST)
    frame = pd.read_csv(CSV, usecols=list(FEATURES) + [TARGET_COLUMN])
    X_test = make_split(frame)["X_test"]
    assert np.array_equal(best.predict(X_test), candidate.predict(X_test))
    assert np.allclose(best.predict_proba(X_test), candidate.predict_proba(X_test))


def test_no_placeholder_scores(evaluation: dict) -> None:
    for key, payload in evaluation["models"].items():
        for name, value in payload["metrics"].items():
            assert isinstance(value, (int, float)), f"{key}.{name} is not a number"
            assert 0.0 <= float(value) <= 1.0, f"{key}.{name} out of range"
        assert payload["metrics"]["recall"] > 0.0, f"{key} reports a zero recall"
