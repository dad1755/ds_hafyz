"""Sprint 2 gate: the 25-column contract, the CSV validator and the quarantine path.

Every malformed fixture asserts the *reason* it was rejected (the error code and the
column the message names), not merely that something raised. The last group of tests
proves the seed CSV is byte-identical before and after a full validation run.
"""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

import pandas as pd
import pytest

from ml import schema
from ml.inspect_dataset import inspect
from ml.schema import (
    COLUMNS,
    COLUMN_SPECS,
    FEATURES,
    ID_COLUMN,
    SEED_CLASS_COUNTS,
    SEED_METADATA_CHECKSUM,
    SEED_ROWS,
    SEED_SHA256,
    TARGET_COLUMN,
    dataset_metadata,
    metadata_checksum,
    spec_for,
)
from src.validation import (
    MAX_UPLOAD_BYTES,
    ValidationError,
    ingest_upload,
    quarantine_upload,
    sanitize_filename,
    validate_csv_bytes,
    validate_dataframe,
    validate_features,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED = REPO_ROOT / "data" / "UCI_Credit_Card.csv"


# --------------------------------------------------------------------------- helpers
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _seed_slice(row_count: int = 3) -> tuple[list[str], list[list[str]]]:
    """Header plus the first ``row_count`` data rows of the real seed file."""
    with SEED.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = [[cell for cell in next(reader)] for _ in range(row_count)]
    return header, rows


def _encode(header: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _valid_payload(row_count: int = 3) -> bytes:
    header, rows = _seed_slice(row_count)
    return _encode(header, rows)


def _mutate(column: str, value: str, row_index: int = 0) -> bytes:
    header, rows = _seed_slice()
    rows[row_index][header.index(column)] = value
    return _encode(header, rows)


def _codes(payload: bytes) -> set[str]:
    return validate_csv_bytes(payload).codes


# --------------------------------------------------------------------------- contract
def test_contract_is_the_ordered_25_columns_and_23_features():
    assert len(COLUMNS) == 25
    assert len(FEATURES) == 23
    assert COLUMNS[0] == ID_COLUMN == "ID"
    assert COLUMNS[-1] == TARGET_COLUMN == "default.payment.next.month"
    assert ID_COLUMN not in FEATURES
    assert TARGET_COLUMN not in FEATURES
    assert "PAY_1" not in COLUMNS, "PAY_1 does not exist in the source and must not be invented"
    assert [c for c in COLUMNS if c.startswith("PAY_") and not c.startswith("PAY_AMT")] == [
        "PAY_0",
        "PAY_2",
        "PAY_3",
        "PAY_4",
        "PAY_5",
        "PAY_6",
    ]
    assert FEATURES == tuple(COLUMNS[1:-1])


def test_documented_code_sets_are_the_observed_and_source_legal_ones():
    assert spec_for("SEX").allowed == frozenset({1, 2})
    assert spec_for("EDUCATION").allowed == frozenset({0, 1, 2, 3, 4, 5, 6})
    assert spec_for("MARRIAGE").allowed == frozenset({0, 1, 2, 3})
    for column in ("PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"):
        assert spec_for(column).allowed == frozenset(range(-2, 10))
        assert spec_for(column).month is not None
    for index in range(1, 7):
        # Signed bills: negative is legal, so there is no lower bound.
        assert spec_for(f"BILL_AMT{index}").minimum is None
        # Payments can never be negative.
        assert spec_for(f"PAY_AMT{index}").minimum == 0
    assert spec_for(TARGET_COLUMN).allowed == frozenset({0, 1})
    assert all(spec.unit in {"NTD", "code", "years", "label", "—"} for spec in COLUMN_SPECS)


# --------------------------------------------------------------------------- seed
def test_seed_dataset_passes_the_contract():
    report = validate_csv_bytes(SEED.read_bytes())
    assert report.ok, report.messages()
    assert report.codes == set()
    assert report.record_count == SEED_ROWS == 30_000
    assert report.column_count == 25
    assert report.class_zero == SEED_CLASS_COUNTS[0] == 23_364
    assert report.class_one == SEED_CLASS_COUNTS[1] == 6_636
    assert report.sha256 == SEED_SHA256
    assert report.metadata_checksum == SEED_METADATA_CHECKSUM
    assert report.metadata() == schema.SEED_METADATA


def test_seed_file_is_byte_identical_after_validation():
    before = _sha256(SEED)
    assert before == SEED_SHA256
    validate_csv_bytes(SEED.read_bytes())
    inspect(SEED)
    after = _sha256(SEED)
    assert after == before == SEED_SHA256
    assert SEED.stat().st_size == 2_862_995


def test_metadata_checksum_is_reproducible_and_identity_bearing():
    first = metadata_checksum(
        dataset_metadata(sha256=SEED_SHA256, record_count=30_000, class_zero=23_364, class_one=6_636)
    )
    second = metadata_checksum(
        dataset_metadata(sha256=SEED_SHA256, record_count=30_000, class_zero=23_364, class_one=6_636)
    )
    assert first == second == SEED_METADATA_CHECKSUM
    changed = metadata_checksum(
        dataset_metadata(sha256=SEED_SHA256, record_count=30_000, class_zero=23_365, class_one=6_635)
    )
    assert changed != SEED_METADATA_CHECKSUM


def test_inspect_dataset_cli_report_passes_all_checks():
    report = inspect(SEED)
    assert report["all_checks_pass"] is True, [
        check for check in report["checks"] if not check["pass"]
    ]
    assert report["row_count"] == 30_000
    assert report["predictors"] == list(FEATURES)
    assert report["metadata_checksum"] == SEED_METADATA_CHECKSUM


# --------------------------------------------------------------------------- malformed
def test_valid_subset_passes():
    report = validate_csv_bytes(_valid_payload())
    assert report.ok, report.messages()
    assert report.record_count == 3


def test_missing_column_is_rejected_for_that_reason():
    header, rows = _seed_slice()
    index = header.index("PAY_3")
    header = header[:index] + header[index + 1 :]
    rows = [row[:index] + row[index + 1 :] for row in rows]
    report = validate_csv_bytes(_encode(header, rows))
    assert report.codes == {"missing_column"}
    assert "PAY_3" in report.errors[0].message


def test_extra_column_is_rejected_for_that_reason():
    header, rows = _seed_slice()
    report = validate_csv_bytes(_encode(header + ["EXTRA_FIELD"], [row + ["0"] for row in rows]))
    assert report.codes == {"extra_column"}
    assert "EXTRA_FIELD" in report.errors[0].message


def test_duplicate_header_is_rejected_for_that_reason():
    header, rows = _seed_slice()
    header[header.index("AGE")] = "SEX"  # duplicate SEX, AGE now absent
    report = validate_csv_bytes(_encode(header, rows))
    assert report.codes == {"duplicate_column"}
    assert "SEX" in report.errors[0].message


def test_wrong_column_order_is_rejected_for_that_reason():
    header, rows = _seed_slice()
    first, second = header.index("PAY_0"), header.index("PAY_2")
    header[first], header[second] = header[second], header[first]
    for row in rows:
        row[first], row[second] = row[second], row[first]
    report = validate_csv_bytes(_encode(header, rows))
    assert report.codes == {"column_order"}


def test_wrong_target_value_is_rejected_for_that_reason():
    report = validate_csv_bytes(_mutate(TARGET_COLUMN, "2"))
    assert report.codes == {"invalid_target_value"}
    assert TARGET_COLUMN in report.errors[0].message


def test_nan_cell_is_rejected_for_that_reason():
    report = validate_csv_bytes(_mutate("BILL_AMT2", ""))
    assert report.codes == {"missing_value"}
    assert report.errors[0].column == "BILL_AMT2"
    assert report.errors[0].rows == 1


def test_unsupported_code_is_rejected_for_that_reason():
    report = validate_csv_bytes(_mutate("EDUCATION", "9"))
    assert report.codes == {"unsupported_code"}
    assert report.errors[0].column == "EDUCATION"


def test_non_finite_value_is_rejected_for_that_reason():
    report = validate_csv_bytes(_mutate("BILL_AMT1", "inf"))
    assert report.codes == {"non_finite"}


def test_non_numeric_value_is_rejected_for_that_reason():
    report = validate_csv_bytes(_mutate("AGE", "unknown"))
    assert report.codes == {"not_numeric"}
    assert report.errors[0].column == "AGE"


def test_negative_payment_is_rejected_for_that_reason():
    report = validate_csv_bytes(_mutate("PAY_AMT1", "-1"))
    assert report.codes == {"out_of_range"}
    assert report.errors[0].column == "PAY_AMT1"


def test_negative_bill_is_accepted():
    assert _codes(_mutate("BILL_AMT3", "-157264")) == set()


def test_oversize_upload_is_rejected_for_that_reason():
    payload = _valid_payload() + b"0" * (MAX_UPLOAD_BYTES + 1)
    report = validate_csv_bytes(payload)
    assert report.codes == {"file_too_large"}
    assert str(MAX_UPLOAD_BYTES) in report.errors[0].message


def test_empty_file_is_rejected_for_that_reason():
    assert _codes(b"") == {"empty_file"}


def test_header_only_file_is_rejected_for_that_reason():
    header, _ = _seed_slice()
    assert _codes(_encode(header, [])) == {"empty_data"}


def test_non_utf8_upload_is_rejected_for_that_reason():
    assert _codes(b"\xff\xfe\x00bad" + _valid_payload()) == {"not_utf8"}


def test_errors_never_echo_cell_values():
    report = validate_csv_bytes(_mutate("EDUCATION", "9"))
    message = report.errors[0].message
    assert "9" not in message
    assert all("9" not in text for text in report.messages() if text is message)


# --------------------------------------------------------------------------- dataframe path
def test_dataframe_path_matches_the_csv_path():
    frame = pd.read_csv(io.BytesIO(_valid_payload()), encoding="utf-8-sig")
    report = validate_dataframe(frame)
    assert report.ok, report.messages()
    assert report.record_count == 3
    assert report.column_count == 25


def test_dataframe_missing_column_is_rejected():
    frame = pd.read_csv(io.BytesIO(_valid_payload()), encoding="utf-8-sig").drop(columns=["MARRIAGE"])
    report = validate_dataframe(frame)
    assert report.codes == {"missing_column"}


# --------------------------------------------------------------------------- features
def _seed_feature_record() -> dict[str, int]:
    header, rows = _seed_slice(1)
    return {name: int(rows[0][header.index(name)]) for name in FEATURES}


def test_feature_validator_accepts_a_seed_row_in_contract_order():
    record = _seed_feature_record()
    validated = validate_features(record)
    assert list(validated) == list(FEATURES)
    assert len(validated) == 23
    assert validated == record


def test_feature_validator_accepts_form_strings():
    record = {name: str(value) for name, value in _seed_feature_record().items()}
    assert validate_features(record) == _seed_feature_record()


def test_feature_validator_rejects_a_missing_feature():
    record = _seed_feature_record()
    del record["PAY_4"]
    with pytest.raises(ValidationError) as caught:
        validate_features(record)
    assert caught.value.code == "missing_feature"
    assert "PAY_4" in caught.value.message


def test_feature_validator_rejects_an_unknown_key():
    record = _seed_feature_record()
    record["ID"] = 1
    with pytest.raises(ValidationError) as caught:
        validate_features(record)
    assert caught.value.code == "unknown_feature"


def test_feature_validator_rejects_an_unsupported_code():
    record = _seed_feature_record()
    record["MARRIAGE"] = 9
    with pytest.raises(ValidationError) as caught:
        validate_features(record)
    assert caught.value.code == "unsupported_code"
    assert caught.value.column == "MARRIAGE"


def test_feature_validator_rejects_an_out_of_band_value():
    record = _seed_feature_record()
    record["LIMIT_BAL"] = 5_000
    with pytest.raises(ValidationError) as caught:
        validate_features(record)
    assert caught.value.code == "out_of_range"
    assert "10000" in caught.value.message


def test_feature_validator_rejects_a_non_finite_value():
    record = _seed_feature_record()
    record["BILL_AMT1"] = float("nan")
    with pytest.raises(ValidationError) as caught:
        validate_features(record)
    assert caught.value.code == "non_finite"


def test_feature_validator_rejects_a_boolean():
    record = _seed_feature_record()
    record["SEX"] = True
    with pytest.raises(ValidationError) as caught:
        validate_features(record)
    assert caught.value.code == "not_numeric"


# --------------------------------------------------------------------------- quarantine
def test_quarantine_generates_its_own_name_and_ignores_the_uploaded_one(tmp_path):
    payload = _valid_payload()
    quarantined = quarantine_upload(payload, "../../../etc/passwd", quarantine_dir=tmp_path)
    assert quarantined.path.parent == tmp_path
    assert ".." not in quarantined.path.name
    assert "passwd" not in quarantined.path.name
    assert quarantined.path.name.endswith(".csv")
    assert quarantined.original_filename_safe == "passwd.csv"
    assert quarantined.sha256 == hashlib.sha256(payload).hexdigest()
    assert quarantined.path.read_bytes() == payload
    assert quarantined.path.stat().st_mode & 0o777 == 0o600


def test_quarantine_names_are_unique(tmp_path):
    payload = _valid_payload()
    first = quarantine_upload(payload, "a.csv", quarantine_dir=tmp_path)
    second = quarantine_upload(payload, "a.csv", quarantine_dir=tmp_path)
    assert first.path != second.path
    assert first.sha256 == second.sha256


def test_quarantine_rejects_oversize_and_empty_payloads(tmp_path):
    with pytest.raises(ValidationError) as caught:
        quarantine_upload(b"0" * (MAX_UPLOAD_BYTES + 1), "big.csv", quarantine_dir=tmp_path)
    assert caught.value.code == "file_too_large"
    with pytest.raises(ValidationError) as caught:
        quarantine_upload(b"", "empty.csv", quarantine_dir=tmp_path)
    assert caught.value.code == "empty_file"
    assert list(tmp_path.iterdir()) == []


def test_ingest_quarantines_before_validating_and_reports_the_reason(tmp_path):
    bad = _mutate("EDUCATION", "9")
    quarantined, report = ingest_upload(bad, "book1.csv", quarantine_dir=tmp_path)
    assert report.codes == {"unsupported_code"}
    assert quarantined.path.exists(), "an invalid upload is retained for diagnosis"
    assert quarantined.sha256 == hashlib.sha256(bad).hexdigest()


def test_ingest_accepts_the_seed_through_quarantine(tmp_path):
    payload = SEED.read_bytes()
    quarantined, report = ingest_upload(payload, "UCI_Credit_Card.csv", quarantine_dir=tmp_path)
    assert report.ok, report.messages()
    assert report.record_count == SEED_ROWS
    assert report.metadata_checksum == SEED_METADATA_CHECKSUM
    assert quarantined.original_filename_safe == "UCI_Credit_Card.csv"
    assert quarantined.sha256 == SEED_SHA256
    assert _sha256(SEED) == SEED_SHA256


def test_sanitize_filename_is_a_label_not_a_path():
    assert sanitize_filename("../../etc/passwd") == "passwd.csv"
    assert sanitize_filename("C:\\Users\\x\\Book1.CSV") == "Book1.CSV"
    assert sanitize_filename("") == "upload.csv"
    assert sanitize_filename(None) == "upload.csv"
    assert "/" not in sanitize_filename("a/b/c/d.csv")
    assert len(sanitize_filename("x" * 400 + ".csv")) == 120
