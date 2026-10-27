# 25. References

Draft, Sprint 14. Every source below is cited in the report or in the repository; the dataset
citation is the one recorded in `README.md` and `docs/data_dictionary.md`.

## Dataset

Yeh, I.-C. (2009). *Default of Credit Card Clients* [Dataset]. UCI Machine Learning Repository.
https://doi.org/10.24432/C55S3H — https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients

Yeh, I.-C., & Lien, C.-H. (2009). The comparisons of data mining techniques for the predictive
accuracy of probability of default of credit card clients. *Expert Systems with Applications*,
36(2), 2473–2480. https://doi.org/10.1016/j.eswa.2007.12.020

## Software

Pedregosa, F., et al. (2011). Scikit-learn: Machine learning in Python. *Journal of Machine
Learning Research*, 12, 2825–2830. (scikit-learn 1.9.1 as pinned in `requirements.txt`.)

McKinney, W. (2010). Data structures for statistical computing in Python. *Proceedings of the 9th
Python in Science Conference*, 56–61. (pandas 3.1.0.)

Harris, C. R., et al. (2020). Array programming with NumPy. *Nature*, 585, 357–362. (NumPy 2.5.4.)

Hunter, J. D. (2007). Matplotlib: A 2D graphics environment. *Computing in Science & Engineering*,
9(3), 90–95.

Streamlit (2024–2026). *Streamlit documentation*. https://docs.streamlit.io (Streamlit 1.66.1.)

Biryukov, A., Dinu, D., Khovratovich, D., & Josefsson, S. (2021). *Argon2 memory-hard function for
password hashing and proof-of-work* (RFC 9106). IETF.

Docker Inc. (2026). *Docker Compose specification*. https://docs.docker.com/compose/

Cloudflare (2026). *Cloudflare Tunnel documentation*. https://developers.cloudflare.com/cloudflare-one/

## Method references cited in the text

Saito, T., & Rehmsmeier, M. (2015). The precision-recall plot is more informative than the ROC plot
when evaluating binary classifiers on imbalanced datasets. *PLOS ONE*, 10(3), e0118432.

He, H., & Garcia, E. A. (2009). Learning from imbalanced data. *IEEE Transactions on Knowledge and
Data Engineering*, 21(9), 1263–1284.

Barocas, S., Hardt, M., & Narayanan, A. (2023). *Fairness and Machine Learning: Limitations and
Opportunities*. MIT Press. https://fairmlbook.org

## Project documents (internal, in the repository)

| Document | Role |
|---|---|
| `blueprint.md` | Implementation specification for sprints S0–S16 |
| `Group Project 40%.md` | Assessment authority: 26 report components, rubric A and B |
| `docs/source_of_truth.md` | Precedence rules when two documents disagree |
| `docs/architecture.md` | Design, threat model, deviations |
| `docs/data_dictionary.md` | Column contract and validation rules |
| `docs/preprocessing_contract.md` | Split, transform and artifact contract |
| `docs/inference_contract.md` | Artifact verification, service, risk bands, wording |
| `docs/test_matrix.md` | T01–T12 and adversarial checks, expected vs observed |
| `docs/report_evidence.md` | Claim-by-claim evidence record |
| `docs/rubric_matrix.md` | Rubric crosswalk |
| `docs/deployment.md`, `docs/runbook.md`, `docs/RELEASE_NOTES.md` | Operations |
| `docs/acceptance/S00.md` … `docs/acceptance/S13.md` | Independent acceptance records |

## Note on citation practice

Where a claim rests on this project's own execution, the citation is a file path under `evidence/`
rather than a publication. That is deliberate: a reader can open the file and check the number, which
is not true of a claim attributed to a source that does not contain it.

## Evidence

- `README.md`
- `docs/data_dictionary.md`
- `blueprint.md`
- `Group Project 40%.md`
- `docs/source_of_truth.md`
- `requirements.txt`
