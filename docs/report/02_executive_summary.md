# 2. Executive Summary

Draft, Sprint 14. Every number below is quoted from a file in this repository; the paths are at
the end of the section.

This project builds a working predictive system for one narrow finance question: given 23
historical attributes of a credit-card account, estimate the probability that the account
defaults on its next payment. It is a binary classification task on the public UCI *Default of
Credit Card Clients* dataset — 30,000 accounts from a Taiwanese bank, billing months April to
September 2005, monetary values in New Taiwan Dollars.

The data is imbalanced: 23,364 accounts (77.88%) did not default and 6,636 (22.12%) did. That
single fact shapes every later decision. A model that always answers "no default" scores 77.88%
accuracy and is worthless, so accuracy was not used to choose between candidates. Three
pipelines — logistic regression, a depth-5 decision tree and a 100-tree random forest with
depth 5 — were fitted on a stratified 80/20 split (24,000 training rows, 6,000 held-out rows)
and ranked by mean five-fold cross-validated F1 on the training rows only. The decision tree
ranked first with cross-validated F1 0.4643; on the untouched held-out set it reached accuracy
0.8172, precision 0.6611, recall 0.3557, F1 0.4625 and ROC-AUC 0.7423. It beats the
always-class-0 baseline on the metrics that matter (F1 0.4625 against 0.0, recall 0.3557
against 0.0) and it still misses 855 of the 1,327 accounts that actually defaulted. That is the
honest headline: the system is useful as a screening aid and not as a credit decision.

The model is not a notebook. It is served by a Streamlit application inside Docker Compose,
published through an existing Cloudflare Tunnel at `https://www.aihubcampus.online` with no
published host port. A signed-in user fills in the 23 features, gets a predicted class, an
uncalibrated probability to two decimals, a risk band with supportive advice, the decision
threshold, the model version and three disclosures. An administrator manages accounts (list,
create, edit, reset, deactivate — never delete) and stages dataset versions that are validated
and never trained on. Authentication is Argon2id with server-side sessions and role checks
inside every privileged function, not merely in the navigation.

Verification is by execution, not by assertion. The test suite reached 285 cases, the twelve
required system tests T01–T12 are recorded against a verbatim pytest transcript, adversarial
checks sweep 14 privileged functions with a user token, and every sprint from S0 to S13 has an
independent acceptance record written by a different agent identity from the one that
implemented it. The public deployment is live and was re-verified through the tunnel with a real
browser.

Limitations are stated in §22 and not softened: recall near 0.36 means most defaulters are
missed; the data is 2005 Taiwanese and does not describe current Malaysian lending; the
probability is uncalibrated; demographic features are model inputs and no fairness audit has
been run; and the system is an academic prototype, not a certified decision system.

## Evidence

- `models/metrics.json`
- `models/eda/summary.json`
- `docs/test_matrix.md`
- `docs/acceptance/S13.md`
- `docs/deployment.md`
- `evidence/s13/browser_check.txt`
- `docs/data_dictionary.md`
