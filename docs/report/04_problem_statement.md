# 4. Problem Statement

Draft, Sprint 14.

A credit-card portfolio produces, every month, a table of accounts and their recent behaviour:
credit limit, repayment status for the last six months, statement balances, amounts actually
paid, and a few demographic attributes. One month later, each account either defaulted on the
next payment or did not. The problem is to estimate that probability in advance from the
attributes available at prediction time.

Formally, the task is binary classification. The target is
`default.payment.next.month` with values `{0, 1}`, where 1 means the account defaulted on the next
payment. The 23 predictors are the columns of the UCI dataset other than the row identifier `ID`
and the target itself. The positive class is 1, and it is the minority: 6,636 of 30,000 accounts
(22.12%).

Three properties make this problem harder than it looks, and each one is a design constraint
rather than a remark:

1. **The classes are imbalanced 78:22.** Accuracy is dominated by the majority class: a constant
   "no default" answer reaches 77.88% on this data. Any evaluation that leads with accuracy is
   therefore misleading, and any model selection driven by accuracy would pick the constant
   answer.
2. **The costs are asymmetric but unquantified.** A false negative (a defaulter predicted as safe)
   and a false positive (a safe account flagged) do not cost the same, but the dataset carries no
   cost information, so the threshold cannot be optimised against a real cost function. This
   project fixes the threshold at 0.5, states it on every result, and reports recall and
   precision separately so a reader can see the trade-off rather than a single blended score.
3. **The inputs are historical and foreign.** The data describes Taiwanese accounts in 2005, in
   New Taiwan Dollars. A model fitted to it answers a question about that population. It is not
   evidence about Malaysian accounts in 2026, and the system says so.

The problem the *system* solves is slightly different from the problem the *model* solves, and the
distinction matters for the report: the model estimates a probability, and the system must present
that probability in a way a human can act on without over-trusting it. That is why the deliverable
includes a risk band with supportive advice, three explicit disclosures on every result, and no
automated adverse action of any kind.

## Evidence

- `docs/data_dictionary.md`
- `models/eda/summary.json`
- `models/metrics.json`
- `docs/inference_contract.md`
- `docs/architecture.md`
