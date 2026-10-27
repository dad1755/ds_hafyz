# 16. User Module

Draft, Sprint 14. Implementation: `src/pages_prediction.py`, `src/pages_history.py`,
`src/predictions.py`; evidence: `evidence/s7/` and `evidence/s13/`.

## 16.1 The form is the contract

The prediction page builds all 23 inputs in four groups — credit profile (5), repayment history (6:
`PAY_0`, `PAY_2` … `PAY_6`), statement balances (6), amounts paid (6) — inside four accordions, and
asserts at import time that they cover `ml.schema.FEATURES` exactly once in contract order. A change
to the contract breaks the import instead of silently dropping an input. Every label, unit, billing
month and code meaning is read from `COLUMN_SPECS`; nothing is retyped.

A *Load synthetic demonstrator example* button fills invented round numbers and states on screen
that they are not a row from the dataset and not a real customer. Every field stays editable
afterwards. This matters for the brief's ethical requirement: the system must not invite a real
person's data into a demo.

## 16.2 Validation before the model

`submit_prediction` calls `validate_features` first. A missing number, an impossible age, a negative
limit, an out-of-range code or a non-numeric value raises `ValidationError` naming the field, and the
model is never called. T08 records the observed behaviour: clearing `LIMIT_BAL` produces exactly one
error — `feature 'LIMIT_BAL' has no value` — with the words "rejected before the model was called",
no result panel, and **0** rows written.

## 16.3 The result panel

The panel is `PredictionResult` rendered, not reinterpreted. For the demonstrator row scored by the
shipped artifact it shows:

| Element | Value shown |
|---|---|
| Class | `1` — "Predicted default next month" (with its caveat) |
| Probability | `0.72`, labelled *estimated, uncalibrated* |
| Band | `High`, with its supportive advice and band note |
| Threshold | `0.50` |
| Model version | `aihubcampus-default-risk-1+48ce02563b2a` |
| Disclosures | calibration note, measured false-negative note, "not a credit decision" |

The exact underlying probability for that row is `0.7195348837209302`; the page renders it to two
decimals and the stored `prediction_logs` row carries the same class, probability (compared with
`pytest.approx(…, abs=1e-12)`), tier and version.

## 16.4 History, repeats and privacy

A repeat submission of the same 23 values is not a second row: the page keeps a per-session
fingerprint of the 23 values and returns the row already recorded, saying so. Only class,
probability, band, model version and timestamp are stored — never the inputs. The history page
filters by the user id resolved from the session token inside the query; the function takes no user
argument, so a user cannot ask for someone else's rows. The page states that a row is a model
output, not a record that a customer defaulted.

## 16.5 What the user cannot do

The user's navigation has exactly three sections — Home, Predict default risk, My prediction history
— and no administrator entry. That is presentation; the control is that the admin pages and every
privileged function re-check the role. T01 records the two navigation sets as exact strings, and T03
records the refusal and audit row when a user calls an admin function directly.

## 16.6 Accessibility and layout

Every page was rendered in a real Chromium at 375×812 and 1280×800 with zero horizontal overflow
(`evidence/s7/browser_check.txt`). The evaluation panel uses the Okabe–Ito palette, a distinct hatch
per model and per correct/error cell, every mark labelled with its value, and alt text carrying the
caption. These are reported as observations from those runs, not as a conformance audit — no
screen-reader or WCAG audit was performed, and §22 says so.

## Evidence

- `src/pages_prediction.py`
- `src/pages_history.py`
- `src/predictions.py`
- `evidence/s7/ui_vs_pipeline.txt`
- `evidence/s7/browser_check.txt`
- `evidence/s7/form_375px.png`
- `evidence/s7/result_375px.png`
- `evidence/s7/history_375px.png`
- `evidence/s11/test-results/demo_prediction.txt`
- `evidence/s13/tunnel_user_prediction.png`
- `docs/test_matrix.md`
- `docs/inference_contract.md`
