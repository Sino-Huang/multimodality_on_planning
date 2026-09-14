# Prospective grounding admission correction

V1 screened all 384 frozen candidates and its audited structural selection found
22 disjoint tasks, with both Storage strata missing. All 32 Storage candidates
were rejected by the inherited 200,000 Cartesian-grounding estimate ceiling.
No model outcome was collected.

That estimate describes the historical A* adapters, whereas the current additive
best-first runtime calls `extract_grounded_positive_strips` with
`prune_type_impossible_groundings=True` in `best_first_add.py`. For the first
frozen Storage candidates, the actual constructor and the new counting function
agree:

| Stratum | Historical Cartesian estimate | Actual type-pruned operators |
| --- | ---: | ---: |
| compact / 919000 | 203,000 | 155 |
| expanded / 919100 | 749,177 | 511 |

`panel-protocol-v2.json` prospectively corrects this technical cost metric while
retaining the 200,000 limit, all structural profiles, all seeds, the generated
PDDL tasks, reference budgets and 60-second candidate timeout. It reuses the v1
raw tasks by path and writes new reference/selection reports under `panel-v2`.
V1 failures and selections remain intact. The twelve-domain scope is unchanged.

This is neither a model-score-selected retry nor permission to drop a stratum.
V2 reference screening and independent object-renaming comparison must still
finish; input/render and actual GPU qualification remain pending. The goal
remains a qualified 24-problem panel, subject to explicit feasibility evidence.
