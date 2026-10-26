"""Evidence helper: the four documented bands, their three cutoffs and the gaplessness sweep.

Run from the repository root inside the application image:

    python evidence/s5/boundary_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.recommendations import TIERS, TIER_BOUNDARIES, tier_for  # noqa: E402


def main() -> int:
    print("# the bands as the service applies them")
    print(f"{'band':<10}{'lower (incl)':<14}{'upper':<12}{'upper inclusive':<17}advice")
    for tier in TIERS:
        print(
            f"{tier.label:<10}{tier.lower:<14.2f}{tier.upper:<12.2f}"
            f"{str(tier.upper_inclusive):<17}{tier.advice}"
        )
    print(f"\ncutoffs: {TIER_BOUNDARIES}\n")

    print("# tier_for() at the documented cutoffs and either side of them")
    for probability in (0.0, 0.2499, 0.25, 0.4999, 0.50, 0.7499, 0.75, 0.9999, 1.0):
        print(f"  tier_for({probability:<7}) -> {tier_for(probability).label}")

    print("\n# gaplessness sweep: every probability in [0, 1] at 0.0001 resolution")
    steps = 10_000
    unclassified = 0
    multi_banded = 0
    jumps = 0
    previous = None
    for step in range(steps + 1):
        probability = step / steps
        matches = [tier for tier in TIERS if tier.contains(probability)]
        if not matches:
            unclassified += 1
        elif len(matches) > 1:
            multi_banded += 1
        else:
            index = TIERS.index(matches[0])
            if previous is not None and index - previous > 1:
                jumps += 1
            previous = index
    print(f"  values checked            : {steps + 1:,}")
    print(f"  unclassified (gaps)       : {unclassified}")
    print(f"  matched more than one band: {multi_banded}")
    print(f"  skipped a band            : {jumps}")
    print(f"  RESULT: {'PASS — continuous and gapless' if not (unclassified or multi_banded or jumps) else 'FAIL'}")
    return 0 if not (unclassified or multi_banded or jumps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
