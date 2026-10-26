#!/usr/bin/env python3
"""S5: verify the shipped model artifact before anything is allowed to load it.

`models/best_pipeline.joblib` is a pickle. Loading one executes whatever it references, so
"the app loads the model" is only safe if the bytes are provably the bytes that trusted code
wrote. This tool is that proof. It runs a fixed, ordered list of checks against
`models/model_manifest.json` and the artifact beside it, and it **fails loudly** — non-zero
exit, every failure named — instead of returning a partially trustworthy pipeline.

The checks, in the order they run (each one only runs if the earlier ones passed):

``files_present``
    The manifest and the artifact exist and are regular files, not symlinks.
``manifest_schema``
    A supported ``schema_version`` and every required section present.
``artifact_checksum``
    SHA-256 and byte count of the artifact equal what the manifest records.
``artifact_provenance``
    The manifest records the one trusted creation path (``ml/train.py → ml/evaluate.py``),
    and the artifact is an uncompressed joblib pickle written by that path.
``dataset_identity``
    The manifest's dataset SHA-256 is the immutable seed's, and — when the CSV is on disk —
    the file still hashes to it.
``feature_contract``
    The manifest's ordered 23 features are exactly ``ml.schema.FEATURES``, ``ID`` and the
    target are excluded, and the declared count agrees.
``class_semantics``
    Classes ``0``/``1`` carry the documented labels and caveats, the positive class is 1, the
    threshold is the evaluated 0.5, and a model version is recorded.
``pickle_allowlist``
    Every class the pickle references comes from the allowlisted scientific stack. A
    reference to ``os``, ``posix``, ``subprocess``, ``builtins.eval`` or anything else is a
    failure — this is the "not produced by trusted code" check.
``pipeline_schema``
    The loaded object is a scikit-learn ``Pipeline`` with the documented ``transform`` /
    ``model`` steps, its transform selects the manifest's feature order, and it exposes
    ``predict_proba`` over two classes.
``deterministic_self_check``
    One fixed probe row scores twice with identical probabilities, the probability is a
    finite number in ``[0, 1]`` summing to 1 with its complement, and the class agrees with
    the recorded threshold.
``metrics_consistency`` (only when ``metrics.json`` is present)
    The evaluation record names the same artifact checksum, the same selected model and the
    same threshold as the manifest.

Usage:
    python -m ml.verify_artifact --models-dir models
    python3 ml/verify_artifact.py --models-dir models --csv data/UCI_Credit_Card.csv
    python -m ml.verify_artifact --models-dir models --json     # machine-readable report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

try:  # `python -m ml.verify_artifact` from the repository root
    from ml.schema import FEATURES, ID_COLUMN, SEED_SHA256, TARGET_COLUMN
except ModuleNotFoundError:  # `python3 ml/verify_artifact.py` from the repository root
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ml.schema import FEATURES, ID_COLUMN, SEED_SHA256, TARGET_COLUMN

ARTIFACT_NAME = "best_pipeline.joblib"
MANIFEST_NAME = "model_manifest.json"
METRICS_NAME = "metrics.json"

SUPPORTED_SCHEMA_VERSIONS: tuple[int, ...] = (1,)
THRESHOLD = 0.5
POSITIVE_CLASS = 1
FEATURE_COUNT = 23
DROPPED_COLUMNS = [ID_COLUMN, TARGET_COLUMN]

#: The single trusted creation path, as recorded by `ml/evaluate.py`. A manifest that names
#: anything else was not produced by this project's training code.
TRUSTED_CREATION_PATH = "ml/train.py → ml/evaluate.py; never loaded from an upload"

#: Class labels are the UI wording of blueprint §5 step 9, with the caveat kept separate so
#: a label can never be read as a guarantee.
EXPECTED_CLASSES = {
    "0": "Predicted non-default next month",
    "1": "Predicted default next month",
}
EXPECTED_CLASS_CAVEATS = {
    "0": "This is not a guarantee of payment.",
    "1": "This is not a confirmed delinquency.",
}
EXPECTED_PROBABILITY_LABEL = "Estimated model probability of next-month default"

#: Modules the pickle may reference: the fitted scientific stack, nothing else. `builtins`
#: is allowed only for the handful of immutable constructors numpy's own pickles use — a
#: blanket `builtins` entry would let `builtins.eval` through.
ALLOWED_MODULE_PREFIXES: tuple[str, ...] = ("numpy", "sklearn", "joblib", "pandas", "scipy")
ALLOWED_BUILTIN_NAMES = frozenset(
    {"slice", "set", "frozenset", "bytearray", "bytes", "complex", "range", "dict",
     "list", "tuple", "object", "int", "float", "str", "bool"}
)

#: One fixed, contract-valid probe row. Values are mid-range on purpose so the probe is
#: stable if the artifact is legitimately retrained; only determinism is asserted, never a
#: memorised score.
PROBE: dict[str, int] = {
    "LIMIT_BAL": 50_000,
    "SEX": 2,
    "EDUCATION": 2,
    "MARRIAGE": 2,
    "AGE": 35,
    "PAY_0": 0,
    "PAY_2": 0,
    "PAY_3": 0,
    "PAY_4": 0,
    "PAY_5": 0,
    "PAY_6": 0,
    "BILL_AMT1": 20_000,
    "BILL_AMT2": 19_000,
    "BILL_AMT3": 18_000,
    "BILL_AMT4": 17_000,
    "BILL_AMT5": 16_000,
    "BILL_AMT6": 15_000,
    "PAY_AMT1": 2_000,
    "PAY_AMT2": 2_000,
    "PAY_AMT3": 1_500,
    "PAY_AMT4": 1_500,
    "PAY_AMT5": 1_000,
    "PAY_AMT6": 1_000,
}


# --------------------------------------------------------------------------- report
@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"check": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class VerificationReport:
    """The outcome of every check, in the order they ran."""

    models_dir: Path
    checks: list[Check] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.ok for check in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if not check.ok]

    def add(self, name: str, ok: bool, detail: str) -> bool:
        self.checks.append(Check(name=name, ok=ok, detail=detail))
        return ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "models_dir": str(self.models_dir),
            "ok": self.ok,
            "checks": [check.as_dict() for check in self.checks],
            "context": self.context,
        }

    def render(self) -> str:
        lines = [f"verify_artifact: {self.models_dir}"]
        for check in self.checks:
            lines.append(f"  [{'PASS' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
        if self.context:
            lines.append("  recorded:")
            for key in sorted(self.context):
                lines.append(f"    {key}: {self.context[key]}")
        lines.append(
            "RESULT: "
            + (
                "PASS — the artifact is the one trusted code produced and it scores a "
                "contract frame deterministically"
                if self.ok
                else f"FAIL — {len(self.failures)} check(s) failed; do not load this artifact"
            )
        )
        return "\n".join(lines)


class ArtifactError(RuntimeError):
    """The artifact cannot be trusted. Raised by :func:`load_verified_pipeline`."""


# --------------------------------------------------------------------------- helpers
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_allowed_reference(module: str, name: str) -> bool:
    """Is ``module.name`` inside the allowlisted scientific stack?"""
    if module == "builtins":
        return name in ALLOWED_BUILTIN_NAMES
    return any(module == prefix or module.startswith(prefix + ".") for prefix in ALLOWED_MODULE_PREFIXES)


def _restricted_unpickler_class(record: set[str]) -> type:
    """A joblib unpickler that records — and refuses — every class the pickle references.

    Subclassing joblib's own unpickler keeps numpy-array reconstruction working while
    routing every class lookup through :func:`is_allowed_reference`, so the check and the
    load use exactly the same code path.
    """
    from joblib.numpy_pickle import NumpyUnpickler

    class RestrictedUnpickler(NumpyUnpickler):
        def find_class(self, module: str, name: str) -> Any:
            record.add(f"{module}.{name}")
            if not is_allowed_reference(module, name):
                raise pickle.UnpicklingError(
                    f"artifact references {module}.{name}, which is outside the allowlisted "
                    "scientific stack — this pickle was not produced by ml/train.py"
                )
            return super().find_class(module, name)

    return RestrictedUnpickler


def load_restricted(path: Path, *, record: set[str] | None = None) -> Any:
    """Load a joblib pickle, refusing any class outside the allowlist.

    ``record`` collects every ``module.name`` reference the load touches, which is how
    :func:`verify_models_dir` reports the allowlist check.
    """
    seen: set[str] = set() if record is None else record
    unpickler_class = _restricted_unpickler_class(seen)
    with path.open("rb") as handle:
        unpickler = unpickler_class(str(path), handle, True, mmap_mode=None)
        return unpickler.load()


def _manifest_sections(manifest: Mapping[str, Any]) -> list[str]:
    required = ("schema_version", "artifact", "model", "features", "classes", "dataset")
    return [section for section in required if section not in manifest]


# --------------------------------------------------------------------------- checks
def verify_models_dir(models_dir: Path | str = "models", *, csv: Path | str | None = None) -> VerificationReport:
    """Run every check and return the full report. Never raises on a bad artifact."""
    directory = Path(models_dir)
    report = VerificationReport(models_dir=directory)
    manifest_path = directory / MANIFEST_NAME
    artifact_path = directory / ARTIFACT_NAME
    metrics_path = directory / METRICS_NAME

    # 1 — files
    problems: list[str] = []
    for path in (manifest_path, artifact_path):
        if path.is_symlink():
            problems.append(f"{path.name} is a symlink")
        elif not path.is_file():
            problems.append(f"{path.name} is missing")
    if not report.add(
        "files_present",
        not problems,
        "; ".join(problems) or f"{MANIFEST_NAME} and {ARTIFACT_NAME} are regular files",
    ):
        return report

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        report.add("manifest_schema", False, f"{MANIFEST_NAME} is not valid JSON: {error}")
        return report

    # 2 — manifest schema
    missing = _manifest_sections(manifest)
    version = manifest.get("schema_version")
    if missing:
        report.add("manifest_schema", False, f"missing section(s): {', '.join(missing)}")
        return report
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        report.add(
            "manifest_schema",
            False,
            f"schema_version {version!r} is not supported (expected one of {SUPPORTED_SCHEMA_VERSIONS})",
        )
        return report
    report.add("manifest_schema", True, f"schema_version {version}; every required section present")

    artifact_section = manifest["artifact"]
    model_section = manifest["model"]
    features_section = manifest["features"]

    # 3 — checksum
    observed_sha = sha256_file(artifact_path)
    observed_bytes = artifact_path.stat().st_size
    recorded_sha = artifact_section.get("sha256")
    recorded_bytes = artifact_section.get("bytes")
    checksum_ok = observed_sha == recorded_sha and observed_bytes == recorded_bytes
    report.context["artifact_sha256"] = observed_sha
    report.context["artifact_bytes"] = observed_bytes
    report.context["model_version"] = model_section.get("version")
    if not report.add(
        "artifact_checksum",
        checksum_ok,
        (
            f"sha256 {observed_sha[:16]}… and {observed_bytes:,} bytes match the manifest"
            if checksum_ok
            else f"artifact sha256 {observed_sha[:16]}… / {observed_bytes:,} bytes does not "
            f"match the manifest's {str(recorded_sha)[:16]}… / {recorded_bytes!r} bytes"
        ),
    ):
        return report

    # 4 — provenance and container format
    creation_path = artifact_section.get("creation_path")
    magic = artifact_path.read_bytes()[:2]
    uncompressed = magic == b"\x80\x04" or magic[:1] == b"\x80"
    provenance_ok = creation_path == TRUSTED_CREATION_PATH and uncompressed
    report.add(
        "artifact_provenance",
        provenance_ok,
        (
            "creation path is ml/train.py → ml/evaluate.py and the file is an uncompressed "
            "joblib pickle"
            if provenance_ok
            else f"creation_path {creation_path!r} is not the trusted path "
            f"{TRUSTED_CREATION_PATH!r}, or the artifact is not an uncompressed pickle "
            f"(magic {magic.hex()})"
        ),
    )
    if not provenance_ok:
        return report

    # 5 — dataset identity
    recorded_dataset = manifest["dataset"].get("sha256")
    dataset_ok = recorded_dataset == SEED_SHA256
    dataset_detail = f"manifest records the immutable seed sha256 {SEED_SHA256[:16]}…"
    csv_path = Path(csv) if csv is not None else directory.parent / "data" / "UCI_Credit_Card.csv"
    if dataset_ok and csv_path.is_file():
        observed_dataset = sha256_file(csv_path)
        dataset_ok = observed_dataset == SEED_SHA256
        dataset_detail = (
            f"{csv_path} hashes to the immutable seed sha256 {SEED_SHA256[:16]}…"
            if dataset_ok
            else f"{csv_path} hashes to {observed_dataset[:16]}…, not the seed's {SEED_SHA256[:16]}…"
        )
    elif dataset_ok:
        dataset_detail += f"; {csv_path} is not on disk, so the file itself was not re-hashed"
    report.add("dataset_identity", dataset_ok, dataset_detail)

    # 6 — feature contract
    order = list(features_section.get("order") or [])
    dropped = list(features_section.get("dropped") or [])
    count = features_section.get("count")
    order_ok = (
        order == list(FEATURES)
        and count == FEATURE_COUNT == len(FEATURES)
        and ID_COLUMN not in order
        and TARGET_COLUMN not in order
        and sorted(dropped) == sorted(DROPPED_COLUMNS)
    )
    report.add(
        "feature_contract",
        order_ok,
        (
            f"ordered features are ml.schema.FEATURES ({FEATURE_COUNT}), "
            f"dropped {dropped}"
            if order_ok
            else "the manifest's ordered features, count or dropped columns disagree with "
            "ml.schema (expected the 23 features in ml.schema.FEATURES order, dropping "
            f"{DROPPED_COLUMNS}; got count={count!r}, {len(order)} names, dropped={dropped})"
        ),
    )
    if not order_ok:
        return report

    # 7 — class semantics and threshold
    classes = manifest["classes"]
    caveats = manifest.get("class_caveats") or {}
    probability_label = manifest.get("probability_label")
    threshold = model_section.get("threshold")
    positive = model_section.get("positive_class")
    model_version = model_section.get("version")
    semantics_problems: list[str] = []
    if classes != EXPECTED_CLASSES:
        semantics_problems.append(f"classes are {classes!r}, expected {EXPECTED_CLASSES!r}")
    if caveats != EXPECTED_CLASS_CAVEATS:
        semantics_problems.append(f"class_caveats are {caveats!r}, expected {EXPECTED_CLASS_CAVEATS!r}")
    if probability_label != EXPECTED_PROBABILITY_LABEL:
        semantics_problems.append(
            f"probability_label is {probability_label!r}, expected {EXPECTED_PROBABILITY_LABEL!r}"
        )
    if threshold != THRESHOLD:
        semantics_problems.append(f"threshold is {threshold!r}, expected {THRESHOLD}")
    if positive != POSITIVE_CLASS:
        semantics_problems.append(f"positive_class is {positive!r}, expected {POSITIVE_CLASS}")
    if not isinstance(model_version, str) or not model_version.strip():
        semantics_problems.append("model.version is missing or empty")
    if not report.add(
        "class_semantics",
        not semantics_problems,
        "; ".join(semantics_problems)
        or f"class labels and caveats are the documented wording; threshold {THRESHOLD}; "
        f"positive class {POSITIVE_CLASS}; version {model_version}",
    ):
        return report

    # 8 — pickle allowlist (before any load)
    references: set[str] = set()
    try:
        pipeline = load_restricted(artifact_path, record=references)
    except (pickle.UnpicklingError, ValueError, AttributeError, ImportError) as error:
        report.add("pickle_allowlist", False, f"the artifact could not be unpickled safely: {error}")
        return report
    report.context["pickle_references"] = sorted(references)
    report.add(
        "pickle_allowlist",
        True,
        f"{len(references)} class reference(s), all inside the allowlisted stack "
        f"({', '.join(sorted({ref.rsplit('.', 1)[0] for ref in references}))})",
    )

    # 9 — pipeline schema
    schema_problems = _pipeline_schema_problems(pipeline, order)
    if not report.add(
        "pipeline_schema",
        not schema_problems,
        "; ".join(schema_problems)
        or "a fitted Pipeline(transform=ColumnTransformer, model=estimator) selecting the "
        "manifest's 23 features, with predict_proba over classes [0, 1]",
    ):
        return report

    # 10 — deterministic self-check on one fixed probe row
    probe_problems, probe_detail = _probe_problems(pipeline, threshold)
    report.add("deterministic_self_check", not probe_problems, "; ".join(probe_problems) or probe_detail)
    if probe_problems:
        return report

    # 11 — metrics.json agreement, when the evaluation record is present
    if metrics_path.is_file():
        report.add("metrics_consistency", *_metrics_problems(metrics_path, observed_sha, manifest))
    else:
        report.add(
            "metrics_consistency",
            True,
            f"{METRICS_NAME} is not beside the artifact (it is not shipped in the image); "
            "the manifest alone was cross-checked",
        )
    return report


def _pipeline_schema_problems(pipeline: Any, order: list[str]) -> list[str]:
    """Structural checks on the loaded object. Returns every problem, not the first."""
    from sklearn.pipeline import Pipeline

    problems: list[str] = []
    if not isinstance(pipeline, Pipeline):
        return [f"the artifact holds {type(pipeline).__name__}, not a scikit-learn Pipeline"]
    steps = list(pipeline.named_steps)
    if steps != ["transform", "model"]:
        problems.append(f"pipeline steps are {steps}, expected ['transform', 'model']")
    transform = pipeline.named_steps.get("transform")
    if transform is None or not hasattr(transform, "transformers_"):
        problems.append("the transform step is not a fitted ColumnTransformer")
    else:
        selected = [list(names) for _, _, names in transform.transformers_]
        if selected != [order]:
            problems.append(
                "the transform does not select exactly the manifest's ordered features "
                f"(it selects {selected!r})"
            )
    model = pipeline.named_steps.get("model")
    if model is None or not hasattr(model, "predict_proba"):
        problems.append("the model step has no predict_proba, so no probability could be reported")
    elif list(getattr(model, "classes_", [])) != [0, 1]:
        problems.append(f"the model's classes_ are {getattr(model, 'classes_', None)!r}, expected [0, 1]")
    if not hasattr(pipeline, "feature_names_in_"):
        problems.append("the pipeline did not record the feature names it was fitted on")
    elif list(pipeline.feature_names_in_) != order:
        problems.append(
            f"the pipeline was fitted on {list(pipeline.feature_names_in_)!r}, not the manifest order"
        )
    return problems


def _probe_frame(order: Iterable[str]) -> Any:
    import pandas as pd

    return pd.DataFrame([[PROBE[name] for name in order]], columns=list(order), dtype="int64")


def _probe_problems(pipeline: Any, threshold: Any) -> tuple[list[str], str]:
    """Score the fixed probe twice and assert the probability is sane and repeatable."""
    import math

    frame = _probe_frame(pipeline.feature_names_in_)
    problems: list[str] = []
    first = pipeline.predict_proba(frame)
    second = pipeline.predict_proba(frame)
    if first.shape != (1, 2):
        return [f"predict_proba returned shape {first.shape}, expected (1, 2)"], ""
    probability = float(first[0, 1])
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        problems.append(f"the probe probability {probability!r} is not a finite value in [0, 1]")
    if abs(float(first[0, 0]) + probability - 1.0) > 1e-9:
        problems.append("the two class probabilities do not sum to 1")
    if float(first[0, 1]) != float(second[0, 1]):
        problems.append("scoring the same row twice returned different probabilities")
    predicted = int(pipeline.predict(frame)[0])
    expected_class = POSITIVE_CLASS if probability >= float(threshold) else 0
    if predicted != expected_class:
        problems.append(
            f"predict() returned {predicted} while the probability {probability:.6f} at "
            f"threshold {threshold} implies {expected_class}"
        )
    return problems, (
        f"probe row scored {probability:.6f} twice with the same value; class {predicted} "
        f"agrees with threshold {threshold}"
    )


def _metrics_problems(metrics_path: Path, artifact_sha: str, manifest: Mapping[str, Any]) -> tuple[bool, str]:
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return False, f"{METRICS_NAME} is not valid JSON: {error}"
    problems: list[str] = []
    recorded = (metrics.get("checks") or {}).get("artifact") or {}
    if recorded.get("sha256") != artifact_sha:
        problems.append(
            f"{METRICS_NAME} records artifact sha256 {str(recorded.get('sha256'))[:16]}…, "
            f"the artifact is {artifact_sha[:16]}…"
        )
    evaluation = metrics.get("evaluation") or {}
    if evaluation.get("selected") != manifest["model"].get("selected"):
        problems.append(
            f"{METRICS_NAME} evaluates {evaluation.get('selected')!r}, the manifest ships "
            f"{manifest['model'].get('selected')!r}"
        )
    if evaluation.get("threshold") != manifest["model"].get("threshold"):
        problems.append(
            f"{METRICS_NAME} evaluated threshold {evaluation.get('threshold')!r}, the manifest "
            f"records {manifest['model'].get('threshold')!r}"
        )
    if problems:
        return False, "; ".join(problems)
    return True, f"{METRICS_NAME} names the same artifact, selected model and threshold"


# --------------------------------------------------------------------------- entry points
def load_verified_pipeline(models_dir: Path | str = "models", *, csv: Path | str | None = None) -> tuple[Any, dict[str, Any]]:
    """Verify, then load. Returns ``(pipeline, manifest)``.

    This is the only supported way for application code to obtain the model: verification
    and loading share one code path, so a failing check can never be skipped by loading
    directly. Raises :class:`ArtifactError` with every failure named.
    """
    report = verify_models_dir(models_dir, csv=csv)
    if not report.ok:
        details = "\n".join(f"  - {check.name}: {check.detail}" for check in report.failures)
        raise ArtifactError(f"model artifact failed verification:\n{details}")
    manifest_path = Path(models_dir) / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pipeline = load_restricted(Path(models_dir) / ARTIFACT_NAME)
    return pipeline, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify models/best_pipeline.joblib against its manifest and fail loudly."
    )
    parser.add_argument("--models-dir", default="models", type=Path)
    parser.add_argument(
        "--csv",
        default=None,
        type=Path,
        help="dataset to re-hash (default: <models-dir>/../data/UCI_Credit_Card.csv when present)",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    report = verify_models_dir(args.models_dir, csv=args.csv)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
