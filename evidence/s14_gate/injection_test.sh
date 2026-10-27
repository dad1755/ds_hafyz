#!/usr/bin/env bash
# S14 gate — does the sprint's tightened checker actually catch a fabricated claim?
#
# Runs entirely on a throwaway export of HEAD (`git archive`), never on the working
# tree, so nothing here can be committed by accident. Five cases:
#
#   A  a paragraph asserting work is done, with no cited path       -> expect FAIL
#   B  a bare whole-word PASS on its own line                       -> expect FAIL
#   C  a PASS claim followed by an unrelated path that does exist   -> measured
#   D  one figure replaced by another valid figure, at one site     -> measured
#   E  a figure removed from every draft                            -> expect FAIL
#
# "measured" means the checker's behaviour is recorded as-is: C and D are the two
# holes this gate found in the sprint's own tooling.
set -u
cd "$(dirname "$0")/../.." || exit 1
SRC=$PWD
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

export_tree() {
    rm -rf "$WORK/tree"
    mkdir -p "$WORK/tree"
    git -C "$SRC" archive HEAD | tar -x -C "$WORK/tree"
}

run_refs() { ( cd "$WORK/tree" && python3 evidence/s14/check_report_refs.py ); }
run_numbers() { ( cd "$WORK/tree" && python3 evidence/s14/check_report_numbers.py ); }

echo "======================================================================"
echo "S14 GATE — injection tests against the sprint's own checkers"
echo "source tree: $SRC at $(git -C "$SRC" rev-parse --short HEAD)"
echo "work copy  : a git-archive export, discarded on exit"
echo "======================================================================"

echo
echo "--- baseline: unmodified export"
export_tree
run_refs | tail -3
run_numbers | tail -3

echo
echo "--- A: fabricated 'done' paragraph appended to 12_evaluation.md"
export_tree
cat >> "$WORK/tree/docs/report/12_evaluation.md" <<'EOF'

## Injected test paragraph

The model is fully implemented and all tests pass. The fourteen-day plan was met by four members.

This result is PASS. See `evidence/s14/this_path_does_not_exist.txt`.
EOF
run_refs | sed -n '/problem/,$p'
echo "EXIT=${PIPESTATUS[0]}"

echo
echo "--- B: a bare whole-word PASS with no cited path"
export_tree
printf '\nThe whole suite is PASS with no exceptions.\n' >> "$WORK/tree/docs/report/12_evaluation.md"
run_refs | sed -n '/problem/,$p'

echo
echo "--- C: PASS followed by a path that exists but says nothing about it"
export_tree
printf '\nThe whole suite is PASS. See `docs/architecture.md`.\n' >> "$WORK/tree/docs/report/12_evaluation.md"
run_refs | tail -3
echo "(the tightened rule is line-scoped: any existing path on the line satisfies it)"

echo
echo "--- D: 0.7665 replaced by 0.7600 in 12_evaluation.md only"
export_tree
python3 - "$WORK/tree" <<'EOF'
import sys, pathlib
p = pathlib.Path(sys.argv[1]) / "docs/report/12_evaluation.md"
p.write_text(p.read_text().replace("0.7665", "0.7600"))
EOF
run_numbers | tail -4
echo "(the checker asserts presence somewhere in the corpus, not presence at the right site)"

echo
echo "--- E: 0.7665 removed from every draft"
export_tree
python3 - "$WORK/tree" <<'EOF'
import sys, pathlib
for p in (pathlib.Path(sys.argv[1]) / "docs/report").glob("*.md"):
    text = p.read_text()
    if "0.7665" in text:
        p.write_text(text.replace("0.7665", "0.7600"))
EOF
run_numbers | sed -n '/FAIL\|expected/p'
echo
echo "======================================================================"
echo "Conclusion: A, B and E are caught; C and D are not. Both holes are"
echo "recorded as findings in docs/acceptance/S14.md, not as product defects."
echo "======================================================================"
