#!/usr/bin/env bash
# Where do the rejected draft-v3 statistics appear?
#
#   bash evidence/s10/draft_grep.sh > evidence/s10/draft_grep.txt 2>&1
#
# The card requires that no v3 draft statistic is hard-coded in the page. This prints the
# search for each of them across the S10 surface (`app.py` and `src/`), then shows where they
# legitimately live: `docs/report_evidence.md` (which labels the drafts as `claimed`, not
# evidence) and the extracted draft text under `evidence/s0/`.
set -uo pipefail
cd "$(dirname "$0")/../.."

NUMBERS=(
  "4432" "4,432" "856" "471" "241"
  "0.661517" "0.354936" "0.461991"
  "167,484.32" "167484.32" "51,223.33" "51223.33" "73,635.86" "73635.86"
  "81.72" "35.49" "46.20" "68.01" "77.88" "22.12"
)

echo "1. The page's own code — app.py and src/ — searched for each draft statistic"
echo "   \$ grep -rnE '<number>' app.py src/"
offenders=0
for number in "${NUMBERS[@]}"; do
  # A number must stand alone: 471 must not match 4712, and 0.661517 must not match 10.661517.
  hits="$(grep -rnE -- "(^|[^0-9.])${number//./\\.}([^0-9]|$)" app.py src/ 2>/dev/null || true)"
  if [ -n "$hits" ]; then
    echo "   MATCH  ${number}"
    printf '%s\n' "$hits" | sed 's/^/          /'
    offenders=$((offenders + 1))
  fi
done
if [ "$offenders" -eq 0 ]; then
  echo "   no match for any of the ${#NUMBERS[@]} draft statistics in app.py or src/"
else
  echo "   $offenders draft statistic(s) found in the page's own code"
fi

echo
echo "2. Where the drafts' numbers do live — reference material, labelled as claimed"
echo "   \$ grep -nE '<number>' docs/report_evidence.md evidence/s0/draft_v3_extracted.txt"
for number in "4432" "856" "471" "241" "81.72" "35.49" "46.20" "68.01"; do
  count_docs="$(grep -cE -- "(^|[^0-9.])${number//./\\.}([^0-9]|$)" docs/report_evidence.md 2>/dev/null || true)"
  count_draft="$(grep -cE -- "(^|[^0-9.])${number//./\\.}([^0-9]|$)" evidence/s0/draft_v3_extracted.txt 2>/dev/null || true)"
  printf '   %-8s docs/report_evidence.md: %-3s  evidence/s0/draft_v3_extracted.txt: %s\n' \
    "$number" "$count_docs" "$count_draft"
done
echo
echo "   The report-evidence file's own words on the drafts:"
grep -n "Both .docx files are drafts\|draft, not proof" docs/report_evidence.md | sed 's/^/     /'

echo
echo "3. The record the page actually reads — these are the real counts, and they differ"
echo "   \$ python -c '<read models/metrics.json>'"
python3 - <<'PY'
import json
record = json.load(open("models/metrics.json", encoding="utf-8"))
for name in ("decision_tree", "logistic_regression", "random_forest"):
    matrix = record["evaluation"]["models"][name]["confusion_matrix"]
    print(f"   {name:20s} TN {matrix['tn']:,}  FP {matrix['fp']:,}  "
          f"FN {matrix['fn']:,}  TP {matrix['tp']:,}")
print(f"   the v3 draft asserts TN 4,432  FP 241  FN 856  TP 471 for the decision tree")
PY

echo
if [ "$offenders" -eq 0 ]; then
  echo "RESULT: PASS — 0 draft-v3 statistics in app.py or src/; the page can only have read them"
  exit 0
fi
echo "RESULT: FAIL — the page's own code carries draft statistics"
exit 1
