# 22. Limitations

Draft, Sprint 14. This section exists so that the weaknesses are in one place, with their numbers,
rather than distributed as hedges.

## 22.1 The model misses most defaulters

Recall on the held-out set is **0.3557**: of 1,327 accounts that defaulted, 855 were predicted as
non-default. Precision is 0.6611, so 242 of 714 flagged accounts did not default. At threshold 0.5
this is a screening aid, not a detector. An objective of recall above 0.60 was set and **not met**
(§5, O13). Raising recall by lowering the threshold is possible but would need validation-only
evidence this project did not produce, so the threshold stays at 0.5 and is displayed.

## 22.2 The probability is uncalibrated

No reliability curve, Brier score or calibration step was produced. The number shown to the user is
a model score between 0 and 1, labelled "estimated, uncalibrated". The four risk bands are
illustrative UI ranges, not validated banking thresholds, and they inherit the score's
uncalibrated status.

## 22.3 The data is historical, foreign and small

30,000 accounts from one Taiwanese bank, billing months April–September 2005, amounts in NTD. Nothing
in this report supports applying the model to Malaysian accounts in 2026, to a different product, or
to a different economic period. There is no temporal validation: one random split, one seed. A model
fitted on 2005 data and tested on 2005 data says nothing about drift.

## 22.4 Fairness is not established

`SEX`, `EDUCATION`, `MARRIAGE` and `AGE` are model inputs. No subgroup metrics, no equal-opportunity
or demographic-parity measurement and no ablation were run. The EDA shows association, not causation,
and the system's protection is procedural (supportive advice, human review, no automated action)
rather than statistical. A reader must not conclude the model is fair.

## 22.5 The modelling ambition is modest

`PAY_0` alone carries 68.01% of the tree's importance; the model is largely a recoding of recent
repayment status. Three algorithms with pre-chosen defaults were compared; there was no
hyperparameter search, no gradient boosting, no feature engineering, no one-hot encoding of the
non-ordinal codes, and no attempt to exploit the six-month panel structure. A stronger model is
plausibly available; the project did not build one.

## 22.6 Testing is broad but not deep

285 automated cases, twelve mapped system tests and a set of adversarial probes. There is no load
test, no soak test, no cross-browser matrix (Chromium only), no screen-reader or WCAG audit, no
penetration test and no user-acceptance study. Security claims are targeted assertions, not an audit.

## 22.7 Operational and platform limits

- **Single instance, single SQLite file.** No high availability, no horizontal scaling, no queue.
- **Cold start is slow.** First paint measured at 4 m 15 s on an idle container while the Matplotlib
  font cache rebuilds; later sessions ~3 s.
- **Three known deployment findings are unfixed** (`docs/deployment.md` §10.5): a hard refresh signs
  the user out because the session token lives only in Streamlit `session_state` (F-1); the XSRF
  cookie is issued without `Secure` because TLS terminates at the edge (F-2); `http://` answers 200
  instead of redirecting (F-3). F-2 and F-3 are operator zone settings.
- **No retention policy.** Audit and prediction rows are never purged.
- **The browser harness is fragile under load** (F-6 in `docs/acceptance/S13.md`).

## 22.8 "Production-like" is not "production"

The container is hardened and publicly reachable, and it is not certified, audited, monitored beyond
a healthcheck, backed by an SLA, or approved for real lending. The brief asks for a working
prototype; this is one, and the report says so in those words.

## Evidence

- `models/metrics.json`
- `models/eda/summary.json`
- `docs/deployment.md`
- `docs/acceptance/S13.md`
- `docs/architecture.md`
- `docs/test_matrix.md`
- `evidence/s4/feature_importances.txt`
- `docs/inference_contract.md`
