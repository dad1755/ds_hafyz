# 3. Introduction

Draft, Sprint 14.

Credit-card issuers decide, every month and at scale, which accounts are likely to miss the next
payment. The decision is consequential for both sides: an issuer that misses a default loses
principal, and an account wrongly treated as a defaulter loses access to credit it could have
served. Predictive analytics is the standard tool for that decision, because the inputs are
structured, historical and plentiful, and because the outcome is binary and observable one month
later.

This project takes one public dataset from that domain and builds the whole chain around it: data
contract, validation, exploratory analysis, three candidate classifiers, a fair held-out
evaluation, a verified model artifact, an authenticated two-role web application, a staged dataset
manager, an evaluation panel that renders the real numbers, a test matrix, a hardened container
and a public HTTPS deployment. The deliverable is a working prototype that a signed-in user can
operate, not a notebook and not a slide about one.

Three decisions define the shape of the work.

First, the system predicts and does not decide. Every result carries the class wording "predicted
default next month", an uncalibrated probability, a risk band with supportive advice, the
decision threshold and a statement that no automated credit action follows. The dataset has no
customer identity, and the form is explicitly not a place to type a real customer's record.

Second, the numbers come from execution. The metrics in this report are read from
`models/metrics.json`, which `ml/evaluate.py` wrote after fitting on 24,000 rows and scoring the
6,000 held-out rows once. Where a previous draft of this report asserted a number, the assertion
was recomputed; where it disagreed with the data, the draft was corrected rather than the data
(§19.2).

Third, honesty about what was not achieved is part of the deliverable. The selected model misses
855 of 1,327 defaulters. The data is twenty years old and from another country. Fairness was not
audited. Those facts appear in §22 rather than in a footnote.

The rest of the report follows the required structure: the problem and its scope (§4–§6), the data
and its preparation (§7–§9), the models and their evaluation (§10–§13), the system that serves them
(§14–§17), the testing that checks it (§18), and the discussion, ethics, limitations and future
work that put the result in context (§19–§26).

## Evidence

- `models/metrics.json`
- `docs/architecture.md`
- `docs/data_dictionary.md`
- `docs/report_evidence.md`
