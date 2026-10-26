"""Rule-based risk tiers over the model's probability (blueprint §5, "Recommendation rules").

Four display bands are mapped from the estimated probability. They are a fixed, documented
lookup — not a second model, not a learned mapping and not a classifier of their own.

The table is copied from the blueprint so the code and the report cannot drift:

| Estimated P(default) | Display tier | Supportive user-facing advice                                        |
|----------------------|--------------|---------------------------------------------------------------------|
| 0.00 – 0.2499        | Low          | Continue routine repayment reminders and periodic review.           |
| 0.25 – 0.4999        | Watch        | Review payment schedule and contact customer proactively with a     |
|                      |              | neutral reminder.                                                    |
| 0.50 – 0.7499        | High         | Offer supportive contact and discuss potential payment arrangements.|
| 0.75 – 1.00          | Critical     | Recommend human risk/support specialist review before any action.   |

Three properties are deliberate and are asserted by `tests/test_prediction.py`:

* **Continuous and gapless.** Each tier is a half-open interval ``[lower, upper)`` and the
  top tier closes at 1.0, so every probability in ``[0, 1]`` falls in exactly one tier and
  no value is unclassified — including the printed cutoffs 0.25, 0.50 and 0.75, which
  belong to the *upper* band (0.25 is Watch, 0.50 is High, 0.75 is Critical).
* **Illustrative, not regulatory.** These cutoffs are not validated banking thresholds and
  the tier is never a credit grade.
* **Never an automated sanction.** Advice is supportive and always defers consequential
  action to a human; no tier freezes a limit, rejects an application or penalises anyone.

The predicted *class* is not decided here: it comes from the model's own fixed 0.5
threshold in :mod:`src.inference`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

#: The three documented cutoffs. A probability exactly equal to one of these belongs to
#: the band above it.
TIER_BOUNDARIES: tuple[float, float, float] = (0.25, 0.50, 0.75)


@dataclass(frozen=True)
class RiskTier:
    """One display band.

    ``lower`` is inclusive and ``upper`` is exclusive, except for the top band, where
    ``upper_inclusive`` is set so that 1.0 belongs to it — that is what makes the four bands
    cover ``[0, 1]`` with no gap and no overlap.
    """

    key: str
    label: str
    lower: float
    upper: float
    advice: str
    upper_inclusive: bool = False

    def contains(self, probability: float) -> bool:
        if self.upper_inclusive:
            return self.lower <= probability <= self.upper
        return self.lower <= probability < self.upper

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "lower": self.lower,
            "upper": self.upper,
            "upper_inclusive": self.upper_inclusive,
            "advice": self.advice,
        }


TIERS: tuple[RiskTier, ...] = (
    RiskTier(
        key="low",
        label="Low",
        lower=0.0,
        upper=0.25,
        advice="Continue routine repayment reminders and periodic review.",
    ),
    RiskTier(
        key="watch",
        label="Watch",
        lower=0.25,
        upper=0.50,
        advice=(
            "Review payment schedule and contact customer proactively with a neutral reminder."
        ),
    ),
    RiskTier(
        key="high",
        label="High",
        lower=0.50,
        upper=0.75,
        advice="Offer supportive contact and discuss potential payment arrangements.",
    ),
    RiskTier(
        key="critical",
        label="Critical",
        lower=0.75,
        upper=1.0,
        advice="Recommend human risk/support specialist review before any action.",
        upper_inclusive=True,
    ),
)

TIER_BY_KEY: dict[str, RiskTier] = {tier.key: tier for tier in TIERS}

#: Rendered next to every tier. It says what the bands are and — more importantly — what
#: they are not, because a "Critical" label invites exactly the reading it forbids.
TIER_NOTE = (
    "Risk bands are illustrative UI cutoffs on the model's estimated probability. They are "
    "not validated banking thresholds and not regulatory credit grades. The band never "
    "triggers an automated decision: no limit is frozen, no application is rejected and no "
    "customer is sanctioned without a human review."
)


class TierError(ValueError):
    """A probability that cannot be banded. The message names the problem, not a value."""


def _as_probability(probability: Any) -> float:
    if isinstance(probability, bool) or not isinstance(probability, (int, float)):
        raise TierError("the probability must be a real number between 0 and 1")
    value = float(probability)
    if not math.isfinite(value):
        raise TierError("the probability must be finite")
    if value < 0.0 or value > 1.0:
        raise TierError("the probability must lie between 0 and 1 inclusive")
    return value


def tier_for(probability: Any) -> RiskTier:
    """Return the display band for ``probability``.

    The lookup is a walk over the documented half-open intervals, so it is gapless by
    construction: the only way to reach the next band is to reach its lower bound.
    """
    value = _as_probability(probability)
    for tier in TIERS:
        if tier.contains(value):
            return tier
    raise TierError("no display band covers this probability")  # unreachable for a valid value


def tier_table() -> list[dict[str, Any]]:
    """The four bands as plain data, for documentation and for the admin/report surface."""
    return [tier.as_dict() for tier in TIERS]


def describe_bands() -> str:
    """One-line-per-band rendering used by `ml/verify_artifact.py` and the docs."""
    return "\n".join(
        f"  {tier.lower:.2f}-{tier.upper:.2f}  {tier.label:<9} {tier.advice}" for tier in TIERS
    )
