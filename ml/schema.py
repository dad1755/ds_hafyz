"""Single source of truth for the data contract (blueprint §4, §9 SPRINT 2).

Three things are defined here and nowhere else:

* :data:`COLUMNS` — the ordered 25-column CSV contract of the supplied dataset.
* :data:`FEATURES` — the ordered 23-feature model input (``ID`` and the target excluded).
* :data:`COLUMN_SPECS` — per-column kind, unit, legal code set, hard validation bounds,
  the range observed in the seed CSV, the band the UI form accepts, and the month each
  historical column refers to.

This module deliberately imports nothing outside the standard library. ``ml.inspect_dataset``
must run on a bare Python before the ML environment exists, and ``src.validation`` imports
these same constants, so the seed inspection, the CSV validator and the 23-input form can
never drift apart.

Reference: ``docs/data_dictionary.md`` renders this contract for humans.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

# --------------------------------------------------------------------------- identity
ID_COLUMN = "ID"
TARGET_COLUMN = "default.payment.next.month"

#: Target semantics: 1 = the account defaulted on the *next* month's payment,
#: 0 = it did not. There is no other legal value in the source.
TARGET_VALUES: tuple[int, ...] = (0, 1)
TARGET_LABELS: dict[int, str] = {
    0: "no default next month",
    1: "default next month",
}

# --------------------------------------------------------------------------- codes
#: ``SEX`` is a two-value dataset code. It is never used to drive a recommendation.
SEX_LABELS: dict[int, str] = {1: "male", 2: "female"}

#: ``EDUCATION`` codes 0, 5 and 6 are undocumented in the UCI distribution but present
#: in the data; they are kept as legal codes rather than silently remapped.
EDUCATION_LABELS: dict[int, str] = {
    0: "unknown / undocumented",
    1: "graduate school",
    2: "university",
    3: "high school",
    4: "others",
    5: "unknown / undocumented",
    6: "unknown / undocumented",
}

#: ``MARRIAGE`` code 0 is present in the data and treated as unknown/other.
MARRIAGE_LABELS: dict[int, str] = {
    0: "unknown / other",
    1: "married",
    2: "single",
    3: "others",
}

#: Repayment-status codes shared by PAY_0, PAY_2 … PAY_6. Observed values are −2 … 8;
#: 9 ("nine months or more of delay") is legal by the source's documented scale even
#: though it does not occur in this sample.
PAY_STATUS_LABELS: dict[int, str] = {
    -2: "no consumption that month",
    -1: "paid in full that month",
    0: "revolving credit (minimum payment)",
    1: "one month of delay",
    2: "two months of delay",
    3: "three months of delay",
    4: "four months of delay",
    5: "five months of delay",
    6: "six months of delay",
    7: "seven months of delay",
    8: "eight months of delay",
    9: "nine months or more of delay",
}

PAY_STATUS_CODES = frozenset(PAY_STATUS_LABELS)

#: Statement/payment month each historical column refers to. The source covers the six
#: months April–September 2005; ``PAY_1`` does not exist and must not be invented.
MONTHS: dict[str, str] = {
    "PAY_0": "Sep 2005",
    "PAY_2": "Aug 2005",
    "PAY_3": "Jul 2005",
    "PAY_4": "Jun 2005",
    "PAY_5": "May 2005",
    "PAY_6": "Apr 2005",
    "BILL_AMT1": "Sep 2005",
    "BILL_AMT2": "Aug 2005",
    "BILL_AMT3": "Jul 2005",
    "BILL_AMT4": "Jun 2005",
    "BILL_AMT5": "May 2005",
    "BILL_AMT6": "Apr 2005",
    "PAY_AMT1": "Sep 2005",
    "PAY_AMT2": "Aug 2005",
    "PAY_AMT3": "Jul 2005",
    "PAY_AMT4": "Jun 2005",
    "PAY_AMT5": "May 2005",
    "PAY_AMT6": "Apr 2005",
}


# --------------------------------------------------------------------------- column specs
@dataclass(frozen=True)
class ColumnSpec:
    """One column of the file contract.

    ``kind`` drives validation:

    ``id``
        Technical identifier — excluded from training and from the UI form.
    ``amount``
        Non-negative whole NTD amount (credit limit).
    ``signed_amount``
        Whole NTD amount that may legitimately be negative (a credit balance).
    ``nonnegative_amount``
        Whole NTD payment amount; cannot be negative.
    ``code``
        Small integer code set (``SEX``, ``EDUCATION``, ``MARRIAGE``).
    ``status_code``
        Signed repayment status code set (``PAY_*``).
    ``target``
        Binary label.
    """

    name: str
    kind: str
    unit: str
    description: str
    allowed: frozenset[int] | None = None
    minimum: int | None = None
    maximum: int | None = None
    observed: tuple[int, int] | None = None
    form: tuple[int, int] | None = None
    month: str | None = None

    @property
    def is_feature(self) -> bool:
        return self.name not in (ID_COLUMN, TARGET_COLUMN)


COLUMN_SPECS: tuple[ColumnSpec, ...] = (
    ColumnSpec(
        name=ID_COLUMN,
        kind="id",
        unit="—",
        description="Technical row identifier. Excluded from training and from the UI form.",
        observed=(1, 30_000),
    ),
    ColumnSpec(
        name="LIMIT_BAL",
        kind="amount",
        unit="NTD",
        description="Credit limit granted to the account, including supplementary cards.",
        minimum=1,
        observed=(10_000, 1_000_000),
        form=(10_000, 1_000_000),
    ),
    ColumnSpec(
        name="SEX",
        kind="code",
        unit="code",
        description="Dataset gender code. Never used to drive a recommendation.",
        allowed=frozenset(SEX_LABELS),
        observed=(1, 2),
        form=(1, 2),
    ),
    ColumnSpec(
        name="EDUCATION",
        kind="code",
        unit="code",
        description="Education level code, including the undocumented codes 0, 5 and 6.",
        allowed=frozenset(EDUCATION_LABELS),
        observed=(0, 6),
        form=(0, 6),
    ),
    ColumnSpec(
        name="MARRIAGE",
        kind="code",
        unit="code",
        description="Marital status code; 0 is unknown/other and is handled explicitly.",
        allowed=frozenset(MARRIAGE_LABELS),
        observed=(0, 3),
        form=(0, 3),
    ),
    ColumnSpec(
        name="AGE",
        kind="amount",
        unit="years",
        description="Age in whole years. Observed 21–79; the form accepts 18–100.",
        minimum=18,
        maximum=100,
        observed=(21, 79),
        form=(18, 100),
    ),
    *(
        ColumnSpec(
            name=f"PAY_{suffix}",
            kind="status_code",
            unit="code",
            description="Repayment status in the given month; negative codes are meaningful.",
            allowed=PAY_STATUS_CODES,
            observed=(-2, 8),
            form=(-2, 9),
            month=MONTHS[f"PAY_{suffix}"],
        )
        for suffix in ("0", "2", "3", "4", "5", "6")
    ),
    *(
        ColumnSpec(
            name=f"BILL_AMT{index}",
            kind="signed_amount",
            unit="NTD",
            description="Statement balance in the given month. Negative balances are valid.",
            month=MONTHS[f"BILL_AMT{index}"],
        )
        for index in range(1, 7)
    ),
    *(
        ColumnSpec(
            name=f"PAY_AMT{index}",
            kind="nonnegative_amount",
            unit="NTD",
            description="Amount paid in the given month; never negative.",
            minimum=0,
            month=MONTHS[f"PAY_AMT{index}"],
        )
        for index in range(1, 7)
    ),
    ColumnSpec(
        name=TARGET_COLUMN,
        kind="target",
        unit="label",
        description="1 = default on next month's payment, 0 = no default. Never a feature.",
        allowed=frozenset(TARGET_VALUES),
        observed=(0, 1),
    ),
)

#: The ordered 25-column file contract.
COLUMNS: tuple[str, ...] = tuple(spec.name for spec in COLUMN_SPECS)

#: The ordered 23-feature model/UI input contract.
FEATURE_SPECS: tuple[ColumnSpec, ...] = tuple(spec for spec in COLUMN_SPECS if spec.is_feature)
FEATURES: tuple[str, ...] = tuple(spec.name for spec in FEATURE_SPECS)

_SPEC_BY_NAME = {spec.name: spec for spec in COLUMN_SPECS}
_INDEX_BY_NAME = {name: index for index, name in enumerate(COLUMNS)}

assert len(COLUMNS) == 25, f"file contract must have 25 columns, got {len(COLUMNS)}"
assert len(FEATURES) == 23, f"feature contract must have 23 features, got {len(FEATURES)}"
assert ID_COLUMN in COLUMNS and TARGET_COLUMN in COLUMNS
assert ID_COLUMN not in FEATURES and TARGET_COLUMN not in FEATURES


def spec_for(name: str) -> ColumnSpec:
    """Return the :class:`ColumnSpec` for ``name``; ``KeyError`` when it is not a contract column."""
    return _SPEC_BY_NAME[name]


def column_index(name: str) -> int:
    """Position of ``name`` in the 25-column contract."""
    return _INDEX_BY_NAME[name]


def is_feature(name: str) -> bool:
    return name in FEATURES


# --------------------------------------------------------------------------- seed facts
#: Immutable benchmark seed: ``data/UCI_Credit_Card.csv``. Never edited — see
#: ``docs/source_of_truth.md`` precedence rule 5.
SEED_PATH = "data/UCI_Credit_Card.csv"
SEED_SHA256 = "a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1"
SEED_SIZE_BYTES = 2_862_995
SEED_ROWS = 30_000
SEED_CLASS_COUNTS: dict[int, int] = {0: 23_364, 1: 6_636}


def dataset_metadata(
    *,
    sha256: str,
    record_count: int,
    column_count: int = len(COLUMNS),
    class_zero: int,
    class_one: int,
    feature_count: int = len(FEATURES),
) -> dict[str, Any]:
    """Dataset version metadata as stored in ``dataset_versions`` (blueprint §6).

    The key order is irrelevant to :func:`metadata_checksum`, which canonicalises it.
    """
    return {
        "sha256": sha256,
        "record_count": int(record_count),
        "column_count": int(column_count),
        "feature_count": int(feature_count),
        "class_zero": int(class_zero),
        "class_one": int(class_one),
        "columns": list(COLUMNS),
        "features": list(FEATURES),
    }


def metadata_checksum(metadata: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical JSON form of ``metadata``.

    Deterministic across runs, hosts and Python versions because the JSON is written
    with sorted keys, no insignificant whitespace and no floats. This is the
    "reproducible dataset metadata checksum" recorded for every dataset version.
    """
    canonical = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


SEED_METADATA: dict[str, Any] = dataset_metadata(
    sha256=SEED_SHA256,
    record_count=SEED_ROWS,
    class_zero=SEED_CLASS_COUNTS[0],
    class_one=SEED_CLASS_COUNTS[1],
)

#: Checksum of the seed dataset's metadata. Any change to the contract, the file or the
#: class counts changes this value, which is what makes it a usable version identity.
SEED_METADATA_CHECKSUM: str = metadata_checksum(SEED_METADATA)
