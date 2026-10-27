# 24. Conclusion

Draft, Sprint 14.

This project set out to build a machine-learning predictive system in the finance sector, and it
delivered one: a public, authenticated web application that scores a 23-feature credit-card account
for next-month default risk, backed by a reproducible pipeline, a verified model artifact, a
staged dataset manager, an evaluation panel that renders real numbers, a 285-case test suite and a
hardened container published over HTTPS with no exposed origin port.

The measured result is honest and unspectacular. The selected decision tree reaches held-out
accuracy 0.8172, precision 0.6611, recall 0.3557 and F1 0.4625, beating a constant-answer baseline
that already scores 0.7788 accuracy. It misses 855 of the 1,327 accounts that defaulted. Those
numbers define the contribution: the system demonstrates a method and a complete engineering path,
not a strong default detector.

Three things are worth carrying forward from the work.

First, the evaluation discipline is the reusable part. A fixed selection rule applied to training
rows only, an untouched held-out set, a baseline row beside every model, arithmetic checks between
metrics and confusion matrices, and a recall figure reported next to accuracy — together these make
the result checkable by someone who does not trust the author.

Second, the system is honest about itself. Every result states the threshold, the model version, the
calibration status, the measured false-negative rate and the fact that no automated credit decision
follows. The limitations are in §22 rather than in a footnote, and the one objective that was set and
missed — recall above 0.60 — is recorded as missed.

Third, the gaps are named with their next step: fairness analysis and a demographic ablation,
calibration and a cost-based threshold, a stronger model evaluated on the same terms, per-prediction
explanation, and the three deployment findings that remain unfixed. None of them is claimed as done.

The system is a working academic prototype. It is deployed, tested and documented, and it is not
certified, audited for fairness, or fit for real lending — which is exactly what its own interface
tells the person using it.

## Evidence

- `models/metrics.json`
- `docs/test_matrix.md`
- `docs/deployment.md`
- `docs/acceptance/S13.md`
- `evidence/s13/browser_check.txt`
- `docs/report_evidence.md`
