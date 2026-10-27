# 20. Ethical and Privacy Considerations

Draft, Sprint 14. The design-side analysis is `docs/architecture.md` §7 (assets, actors, threat
model T1–T12); the implemented controls are described in §14.4 of this report.

## 20.1 Data privacy and confidentiality

- **No personal data is collected.** The only account attribute is a username and a display name;
  there is no email, phone, address or banking detail, and no registration flow.
- **No real customer record belongs in the system.** The dataset is pseudonymous — `ID` is a
  sequential index, not an identifier — and the form is for synthetic demonstrator values, which
  the interface labels as invented and not from the dataset.
- **Prediction logs store no feature snapshot.** A row keeps class, probability, band, model version
  and timestamp against a user id. The 23 inputs are never persisted, so a database leak exposes
  model outputs, not account attributes.
- **The database is not a downloadable file.** Six candidate paths were probed and all return the
  application shell; none serves the SQLite bytes (`evidence/s11/probe_http.txt`).
- **Secrets stay out of the repository.** Credentials and the tunnel token live in operator files
  that are git-ignored and mode 600; `scripts/check_no_secrets.py` scans every tracked file and
  reports zero hits for the four operator secrets (`evidence/s13/check_no_secrets.txt`).

## 20.2 Responsible use of the prediction

The system is framed, in code and on screen, as decision *support*:

- the class is "predicted default next month", never "will default";
- the probability is labelled estimated and uncalibrated;
- the advice is supportive (contact, payment arrangements, review) and contains no sanction;
- the threshold and the measured false-negative rate are shown on every result;
- no automated action follows a prediction — no limit change, no block, no contact;
- every screen states that the output is not a credit decision.

The false-negative disclosure is the ethical centre of the interface: a model that misses 64% of
defaulters must not be presented as a detector, and the result panel says so rather than leaving a
reader to discover it in the appendix.

## 20.3 Dataset bias and fairness

This is the project's largest unaddressed ethical gap, and it is stated rather than managed:

- **Demographic features are model inputs.** `SEX`, `EDUCATION`, `MARRIAGE` and `AGE` are four of the
  23 features. No fairness audit was run: no subgroup confusion matrices, no equal-opportunity or
  demographic-parity measurement, no ablation showing what the model does without them.
- **The sample is a single bank's customers in 2005.** Any bias in that bank's lending practice is
  inherited by the model.
- **The EDA shows demographic differences but cannot explain them.** Education codes show default
  rates from 5.69% to 25.16%; marriage codes from 20.93% to 26.01%. These are descriptive
  associations in one sample, unadjusted for confounders such as credit limit and repayment history,
  and they are not evidence of a causal effect.
- **The mitigation is procedural, not statistical.** Advice is supportive and human-reviewed; no
  adverse action is automated; and the ablation is named as future work (§23.3) rather than claimed
  as done.

A reader should conclude from this section that the system is *not* demonstrated to be fair, only
that it is prevented from acting unfairly on its own.

## 20.4 Limitations of the prediction, as a matter of honesty

Four statements appear on the result panel and are repeated here: the probability is uncalibrated;
the model misses a large share of defaulters; the data is historical and foreign; and the output is
not a credit decision. Academic integrity and the brief's §13 requirement both point the same way —
a predictive system that overstates itself is a worse artefact than a weaker system that does not.

## 20.5 What is deliberately not claimed

- Not GDPR/PDPA compliant by audit — no such audit was performed; the design minimises data instead.
- Not anonymous — accounts are pseudonymous and audit rows are attributable to a user id.
- Not encrypted at rest beyond the platform's volume; the SQLite file is protected by filesystem
  permissions and the container's isolation, and that is stated plainly rather than implied to be
  more.

## Evidence

- `docs/architecture.md`
- `evidence/s11/probe_http.txt`
- `evidence/s13/check_no_secrets.txt`
- `evidence/s6/security_smoke.txt`
- `src/pages_prediction.py`
- `docs/inference_contract.md`
- `models/eda/summary.json`
- `docs/rubric_matrix.md`
