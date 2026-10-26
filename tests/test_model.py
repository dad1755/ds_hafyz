"""Sprint 5 gate: the shipped artifact matches its manifest and can be trusted before loading.

Two surfaces are asserted here:

* `ml/verify_artifact.py` — the ordered checks, including that a tampered artifact, a
  tampered manifest and a pickle from outside the scientific stack are all rejected loudly
  (non-zero exit) rather than loaded.
* the manifest contract the application reads — ordered 23 features, class labels with
  caveats, the fixed 0.5 threshold, a model version and the recorded evaluation summary.

`tests/test_prediction.py` covers what the service *returns*; this file covers what it
*loads*.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ml.schema import FEATURES, ID_COLUMN, SEED_SHA256, TARGET_COLUMN
from ml.verify_artifact import (
    ARTIFACT_NAME,
    MANIFEST_NAME,
    METRICS_NAME,
    TRUSTED_CREATION_PATH,
    ArtifactError,
    is_allowed_reference,
    load_restricted,
    load_verified_pipeline,
    verify_models_dir,
)
from src.inference import load_service

REPO = Path(__file__).resolve().parent.parent
MODELS = REPO / "models"
MANIFEST = MODELS / MANIFEST_NAME
ARTIFACT = MODELS / ARTIFACT_NAME


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _copy_models(destination: Path) -> Path:
    """A private copy of the three shipped model files, for tampering tests."""
    destination.mkdir(parents=True, exist_ok=True)
    for name in (MANIFEST_NAME, ARTIFACT_NAME, METRICS_NAME):
        shutil.copyfile(MODELS / name, destination / name)
    return destination


def _run_verify(models_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ml.verify_artifact", "--models-dir", str(models_dir)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )


# --------------------------------------------------------------------- manifest contract
def test_manifest_lists_the_23_features_in_contract_order() -> None:
    manifest = _manifest()
    assert manifest["features"]["order"] == list(FEATURES)
    assert manifest["features"]["count"] == 23 == len(FEATURES)
    assert ID_COLUMN not in manifest["features"]["order"]
    assert TARGET_COLUMN not in manifest["features"]["order"]
    assert sorted(manifest["features"]["dropped"]) == sorted([ID_COLUMN, TARGET_COLUMN])


def test_manifest_carries_the_documented_class_wording() -> None:
    manifest = _manifest()
    assert manifest["classes"] == {
        "0": "Predicted non-default next month",
        "1": "Predicted default next month",
    }
    assert manifest["class_caveats"] == {
        "0": "This is not a guarantee of payment.",
        "1": "This is not a confirmed delinquency.",
    }
    assert manifest["probability_label"] == "Estimated model probability of next-month default"
    assert "uncalibrated" in manifest["calibration"]


def test_manifest_records_threshold_version_and_evaluation() -> None:
    manifest = _manifest()
    model = manifest["model"]
    assert model["threshold"] == 0.5
    assert model["positive_class"] == 1
    assert model["version"].startswith("aihubcampus-default-risk-1+")
    # The version suffix is the artifact checksum, so the two cannot drift apart.
    assert model["version"].endswith(manifest["artifact"]["sha256"][:12])
    evaluation = manifest["evaluation"]
    assert evaluation["threshold"] == 0.5
    assert evaluation["test_rows"] == 6000
    assert 0.0 < evaluation["metrics"]["recall"] < 1.0
    assert evaluation["confusion_matrix"]["total"] == 6000


def test_manifest_records_the_trusted_creation_path() -> None:
    assert _manifest()["artifact"]["creation_path"] == TRUSTED_CREATION_PATH


def test_manifest_dataset_is_the_immutable_seed() -> None:
    assert _manifest()["dataset"]["sha256"] == SEED_SHA256


def test_artifact_checksum_matches_the_shipped_bytes() -> None:
    manifest = _manifest()
    digest = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    assert manifest["artifact"]["sha256"] == digest
    assert manifest["artifact"]["bytes"] == ARTIFACT.stat().st_size


# --------------------------------------------------------------------------- verification
def test_verify_artifact_passes_on_the_shipped_models() -> None:
    report = verify_models_dir(MODELS)
    assert report.ok, [check.as_dict() for check in report.failures]
    names = [check.name for check in report.checks]
    assert names == [
        "files_present",
        "manifest_schema",
        "artifact_checksum",
        "artifact_provenance",
        "dataset_identity",
        "feature_contract",
        "class_semantics",
        "pickle_allowlist",
        "pipeline_schema",
        "deterministic_self_check",
        "metrics_consistency",
    ]


def test_verify_artifact_cli_exits_zero() -> None:
    result = _run_verify(MODELS)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT: PASS" in result.stdout


def test_verify_rejects_a_modified_artifact(tmp_path: Path) -> None:
    directory = _copy_models(tmp_path / "models")
    payload = bytearray((directory / ARTIFACT_NAME).read_bytes())
    payload[-1] ^= 0xFF
    (directory / ARTIFACT_NAME).write_bytes(bytes(payload))

    report = verify_models_dir(directory)
    assert not report.ok
    assert [check.name for check in report.failures] == ["artifact_checksum"]
    result = _run_verify(directory)
    assert result.returncode == 1
    assert "FAIL" in result.stdout and "RESULT: FAIL" in result.stdout


def test_verify_rejects_a_manifest_with_a_different_feature_order(tmp_path: Path) -> None:
    directory = _copy_models(tmp_path / "models")
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["features"]["order"] = list(reversed(manifest["features"]["order"]))
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    report = verify_models_dir(directory)
    assert not report.ok
    assert [check.name for check in report.failures] == ["feature_contract"]


def test_verify_rejects_a_manifest_with_an_unknown_creation_path(tmp_path: Path) -> None:
    directory = _copy_models(tmp_path / "models")
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["artifact"]["creation_path"] = "downloaded from somewhere"
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    report = verify_models_dir(directory)
    assert not report.ok
    assert [check.name for check in report.failures] == ["artifact_provenance"]


def test_verify_rejects_a_moved_threshold(tmp_path: Path) -> None:
    directory = _copy_models(tmp_path / "models")
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["model"]["threshold"] = 0.7
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    report = verify_models_dir(directory)
    assert not report.ok
    assert [check.name for check in report.failures] == ["class_semantics"]


# ---------------------------------------------------------------- untrusted pickles
def test_allowlist_admits_the_scientific_stack_and_nothing_else() -> None:
    for module, name in (
        ("numpy", "ndarray"),
        ("numpy._core.multiarray", "_reconstruct"),
        ("sklearn.tree._tree", "Tree"),
        ("sklearn.pipeline", "Pipeline"),
        ("joblib.numpy_pickle", "NumpyArrayWrapper"),
        ("pandas.core.frame", "DataFrame"),
        ("builtins", "slice"),
    ):
        assert is_allowed_reference(module, name), f"{module}.{name} should be allowed"
    for module, name in (
        ("os", "system"),
        ("posix", "system"),
        ("subprocess", "Popen"),
        ("sys", "exit"),
        ("importlib", "import_module"),
        ("ctypes", "CDLL"),
        ("pathlib", "Path"),
        ("builtins", "eval"),
        ("builtins", "exec"),
        ("builtins", "getattr"),
        ("numpyx", "array"),  # a prefix must not match a longer module name
    ):
        assert not is_allowed_reference(module, name), f"{module}.{name} must be refused"


def test_load_restricted_refuses_a_foreign_pickle(tmp_path: Path) -> None:
    hostile = tmp_path / "hostile.joblib"
    hostile.write_bytes(pickle.dumps(subprocess.Popen))
    with pytest.raises(pickle.UnpicklingError, match="subprocess.Popen"):
        load_restricted(hostile)


def _bomb(marker: Path) -> bytes:
    """A pickle whose only job, if it were ever executed, is to write ``marker``."""

    class Bomb:
        def __reduce__(self):
            return (marker.write_text, ("executed",))

    return pickle.dumps(Bomb())


def test_verify_never_executes_an_artifact_whose_checksum_is_wrong(tmp_path: Path) -> None:
    directory = _copy_models(tmp_path / "models")
    marker = tmp_path / "executed.txt"
    (directory / ARTIFACT_NAME).write_bytes(_bomb(marker))

    report = verify_models_dir(directory)
    assert not report.ok
    assert [check.name for check in report.failures] == ["artifact_checksum"]
    assert not marker.exists(), "an unverified pickle was executed"


def test_verify_never_executes_an_artifact_that_matches_a_forged_manifest(tmp_path: Path) -> None:
    """Even when the attacker also rewrites the manifest's checksum, the pickle is refused."""
    directory = _copy_models(tmp_path / "models")
    marker = tmp_path / "executed.txt"
    payload = _bomb(marker)
    (directory / ARTIFACT_NAME).write_bytes(payload)

    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["artifact"]["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest["artifact"]["bytes"] = len(payload)
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    report = verify_models_dir(directory)
    assert not report.ok
    assert [check.name for check in report.failures] == ["pickle_allowlist"]
    assert not marker.exists(), "an allowlist-rejected pickle was executed"


def test_load_verified_pipeline_raises_on_a_tampered_directory(tmp_path: Path) -> None:
    directory = _copy_models(tmp_path / "models")
    payload = bytearray((directory / ARTIFACT_NAME).read_bytes())
    payload[10] ^= 0xFF
    (directory / ARTIFACT_NAME).write_bytes(bytes(payload))

    with pytest.raises(ArtifactError, match="artifact_checksum"):
        load_verified_pipeline(directory)
    with pytest.raises(ArtifactError):
        load_service(directory)


def test_load_verified_pipeline_returns_the_shipped_pipeline() -> None:
    pipeline, manifest = load_verified_pipeline(MODELS)
    assert list(pipeline.named_steps) == ["transform", "model"]
    assert manifest["features"]["order"] == list(FEATURES)


def test_service_refuses_a_directory_that_is_not_an_artifact(tmp_path: Path) -> None:
    empty = tmp_path / "not-a-model"
    empty.mkdir()
    with pytest.raises(ArtifactError, match="files_present"):
        load_service(empty)
