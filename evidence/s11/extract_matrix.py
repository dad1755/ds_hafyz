#!/usr/bin/env python3
"""Build the T01–T12 rows of ``docs/test_matrix.md`` from the raw pytest run.

    python3 evidence/s11/extract_matrix.py > evidence/s11/test-results/t_matrix_extract.txt

The table below is a *claim*: "this test exercises that requirement". The script does not
trust the claim — it reads ``pytest_all_verbose.txt`` (the untouched output of the full run)
and fails if a cited node id is missing or did not report PASSED. Parametrized node ids are
matched by their ``[param]`` suffix so a case that silently disappeared is noticed as a
count change.

Exit codes: 0 = every cited test passed, 1 = a citation is unproven, 2 = no raw run found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "test-results" / "pytest_all_verbose.txt"

# T id -> (requirement, [(node id, what it proves)])
MATRIX: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "T01": (
        "Valid admin and user login, distinct views",
        [
            ("tests/test_integration.py::test_t01_an_admin_and_a_user_sign_in_to_different_navigation",
             "both roles sign in through the page and their navigation tuples are compared"),
            ("tests/test_app_auth.py::test_an_admin_signs_in_and_sees_the_admin_section",
             "the admin's session renders the management section"),
            ("tests/test_app_auth.py::test_a_regular_user_never_sees_the_admin_section",
             "the user's session renders none of it"),
        ],
    ),
    "T02": (
        "Incorrect credentials rejected / throttled",
        [
            ("tests/test_security.py::test_wrong_password_is_rejected_with_a_generic_message",
             "one generic message, no hint about which half was wrong"),
            ("tests/test_security.py::test_five_failures_lock_the_username_even_for_the_right_password",
             "the fifth failure locks the username; a different account is unaffected"),
            ("tests/test_security.py::test_the_lock_expires_by_itself",
             "the lock lifts after the documented window"),
            ("tests/test_app_auth.py::test_a_wrong_password_shows_one_generic_error_and_opens_no_session",
             "the page opens no session on a bad password"),
        ],
    ),
    "T03": (
        "User prohibited from admin screen and underlying privileged functions",
        [
            ("tests/test_adversarial.py::test_every_privileged_function_refuses_a_user_session_and_audits_the_attempt",
             "every privileged function in accounts/data_manager refuses a user token and audits it"),
            ("tests/test_adversarial.py::test_every_privileged_function_refuses_an_anonymous_caller",
             "the same functions refuse an anonymous caller and a forged token"),
            ("tests/test_adversarial.py::test_the_sweep_is_a_real_list_not_an_empty_one",
             "the sweep is not passing because it iterates over nothing"),
            ("tests/test_admin.py::test_a_user_never_sees_the_user_management_section",
             "the admin screen is absent for a user"),
            ("tests/test_admin.py::test_a_user_calling_an_admin_function_is_denied_and_the_attempt_is_audited",
             "calling the function behind the screen is denied and recorded"),
        ],
    ),
    "T04": (
        "Admin adds/edits a user and the change persists",
        [
            ("tests/test_admin.py::test_an_admin_creates_an_account_in_the_ui_and_that_user_then_signs_in",
             "the created account signs in afterwards"),
            ("tests/test_admin.py::test_a_display_name_edit_persists_and_is_audited",
             "an edit is read back from the database and audited"),
            ("tests/test_admin.py::test_the_ui_role_change_persists_and_is_audited",
             "a role change persists and is audited"),
        ],
    ),
    "T05": (
        "Valid 25-column CSV accepted and staged with counts",
        [
            ("tests/test_admin.py::test_the_seed_csv_validates_and_stages_with_its_real_counts",
             "30,000 rows / 25 columns / 23,364 vs 6,636 / seed sha256, staged not activated"),
            ("tests/test_admin.py::test_the_page_stages_an_upload_and_shows_counts_but_no_row",
             "the page shows the counts and never a record"),
        ],
    ),
    "T06": (
        "Missing-column / malformed CSV rejected with a clear reason",
        [
            ("tests/test_admin.py::test_a_missing_column_upload_is_rejected_with_the_reason_recorded",
             "'missing required column(s): PAY_6' persisted with the rejection, no version created"),
            ("tests/test_admin.py::test_a_wrong_target_upload_is_rejected_with_the_reason_recorded",
             "a target value outside {0,1} is rejected with invalid_target_value"),
            ("tests/test_admin.py::test_the_page_lists_a_rejection_with_the_reason_it_was_refused",
             "the refusal reason reaches the screen"),
            ("tests/test_schema.py::test_missing_column_is_rejected_for_that_reason",
             "the validator names the missing column itself"),
        ],
    ),
    "T07": (
        "Valid 23-field submission returns a genuine class/probability/advice",
        [
            ("tests/test_prediction_ui.py::test_the_form_offers_exactly_the_23_contract_features",
             "the form's fields are the contract's 23, in order"),
            ("tests/test_prediction_ui.py::test_the_on_screen_result_equals_the_direct_pipeline_output",
             "class, probability, band, advice, model version and disclosures equal the pipeline"),
        ],
    ),
    "T08": (
        "Invalid age/limit/codes/missing numeric values rejected",
        [
            ("tests/test_prediction_ui.py::test_invalid_input_blocks_the_model_with_a_readable_message",
             "a cleared LIMIT_BAL blocks submission and writes no row"),
            ("tests/test_prediction.py::test_invalid_input_never_reaches_the_model",
             "the service refuses before the pipeline is called"),
            ("tests/test_schema.py::test_feature_validator_rejects_an_out_of_band_value",
             "an out-of-range code/age/limit is refused"),
            ("tests/test_schema.py::test_feature_validator_rejects_a_missing_feature",
             "a missing numeric value is refused"),
        ],
    ),
    "T09": (
        "App class and probability match standalone pipeline output",
        [
            ("tests/test_prediction.py::test_service_matches_the_direct_pipeline_exactly",
             "bit-identical probability and the same class as the raw pipeline"),
            ("tests/test_prediction.py::test_the_cli_agrees_with_the_direct_pipeline",
             "the CLI path agrees too"),
            ("tests/test_prediction_ui.py::test_the_on_screen_result_equals_the_direct_pipeline_output",
             "what the page prints equals the pipeline output for the same row"),
        ],
    ),
    "T10": (
        "Tier mapping and textual recommendation match score boundaries",
        [
            ("tests/test_prediction.py::test_the_three_documented_cutoffs_belong_to_the_band_above",
             "0.25/0.50/0.75 belong to the upper band"),
            ("tests/test_prediction.py::test_bands_are_continuous_at_every_documented_edge",
             "every edge value maps to the documented band"),
            ("tests/test_prediction.py::test_no_probability_falls_between_two_bands",
             "a 10,001-point sweep: exactly one band each, no gap, monotonic"),
        ],
    ),
    "T11": (
        "Restart retains SQLite, model and protected access",
        [
            ("tests/test_integration.py::test_t11_a_restart_keeps_the_database_the_session_and_the_model",
             "a second process resolves the session and re-verifies the same artifact checksum"),
            ("tests/test_security.py::test_the_database_survives_a_restart",
             "the database contents survive a reopen"),
        ],
    ),
    "T12": (
        "Full user login -> prediction -> history -> logout",
        [
            ("tests/test_integration.py::test_t12_full_journey_login_predict_history_logout",
             "one session carries the whole journey; the row survives the sign-out"),
            ("tests/test_integration.py::test_t12_the_prediction_is_refused_before_sign_in",
             "the same journey cannot start before signing in"),
        ],
    ),
}

RESULT = re.compile(r"^(?P<node>\S+::\S+?) (?P<verdict>PASSED|FAILED|ERROR|SKIPPED)")
PARAM = re.compile(r"\[[^\]]*\]$")
TALLY = re.compile(r"^=+ (?P<summary>\d+ (?:passed|failed)[^=]*) =+$", re.M)


def main() -> int:
    if not RAW.is_file():
        print(f"missing raw run: {RAW}", file=sys.stderr)
        return 2
    text = RAW.read_text(encoding="utf-8", errors="replace")

    # A parametrized test reports one line per case, each with a [param] suffix; index by the
    # base node id and keep every case's verdict so a vanished case is visible as a count.
    outcomes: dict[str, list[str]] = {}
    for line in text.splitlines():
        match = RESULT.match(line)
        if match:
            base = PARAM.sub("", match.group("node"))
            outcomes.setdefault(base, []).append(match.group("verdict"))

    tally = TALLY.search(text)
    print(f"raw run: {RAW.relative_to(HERE.parent.parent)}")
    print(f"summary: {tally.group('summary') if tally else 'unknown'}")
    print()
    print("| Test | Requirement | Cited node ids | Observed |")
    print("|---|---|---|---|")

    failures = 0
    for tid, (requirement, citations) in MATRIX.items():
        cells: list[str] = []
        verdicts_seen: list[str] = []
        for node, _proves in citations:
            verdicts = outcomes.get(node)
            if verdicts is None:
                cells.append(f"`{node.split('::')[-1]}` **MISSING FROM THE RUN**")
                verdicts_seen.append("MISSING")
                failures += 1
                continue
            param = f"[{len(verdicts)} cases]" if len(verdicts) > 1 else ""
            cells.append(f"`{node.split('::')[-1]}`{param}")
            distinct = sorted(set(verdicts))
            verdicts_seen.extend(distinct)
            if distinct != ["PASSED"]:
                failures += 1
        verdict = "PASSED" if set(verdicts_seen) == {"PASSED"} else "NOT PROVEN"
        print(f"| {tid} | {requirement} | {'<br>'.join(cells)} | **{verdict}** |")

    print()
    if failures:
        print(f"RESULT: FAIL — {failures} citation(s) unproven")
        return 1
    total = sum(len(v) for v in outcomes.values())
    print(f"RESULT: PASS — every cited test id appears in the raw run as PASSED "
          f"({len(MATRIX)} requirements, {total} executed test cases in the run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
