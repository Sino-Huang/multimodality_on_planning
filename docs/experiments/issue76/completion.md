# Completed multimodal feasibility experiment (#76)

The declared pilot completed all four training runs and all **48 episodes** in
**3,894.99 seconds (64.92 minutes)**, within its four-hour wall-clock cap.
Independent CPU replay verified every retained episode, exact condition/task/seed
coverage, final-adapter bindings, aggregate reports and point metrics. The result
is **VALID_STOP**, with `pilot_complete: true` and `scientific_completion: false`.
This is completed execution with a failed performance gate; no rerun is needed
to turn that negative result into a positive one.

## Scope and results

Each algorithm used exactly 512 declared training records, one epoch, 16 optimizer
updates and seed 17. The existing pilot manifest selected storage, blocksworld and
ferry: nine task groups / 12 algorithm-task cases. Each of exact-reference,
random-valid, pretrained-base and process-SFT conditions has 12 episodes, using
one evaluation seed, 17. All four final adapters are saved.

| Algorithm | SFT success | Random-valid success | Base success | SFT invalid-operation rate |
| --- | ---: | ---: | ---: | ---: |
| BFS | 0/3 | 1/3 | 0/3 | 42.86% |
| BFWS | 0/3 | 2/3 | 0/3 | 100% |
| Additive w3 | 1/3 | 3/3 | 0/3 | 18.18% |
| Additive greedy | 1/3 | 3/3 | 0/3 | 20% |

Exact references succeed in all 12 cases. Every SFT algorithm fails both the
frozen 80% success threshold and the 5% maximum invalid-operation-rate threshold.
The failed learned episodes terminate on deterministic invalid operations.
Some emitted JSON is syntactically well formed but has incorrect operation fields
or runtime state/update choices. Successful JSON generation is not equivalent to
trusted runtime validity. Two learned episodes succeeded; ten did not.

The pilot does not establish a structural/process advantage over its best control.
It also does not establish that multimodal input is worse than visual input: #75
used 43,876 full-corpus records and two epochs, with a larger evaluation panel.
These training schedules are not matched. Under-training is a possible explanation,
not an identified causal result. Low training loss alone did not establish valid
execution on the selected development tasks. No training-seed variance or held-out
generalization claim is supported.

## Runtime validity and resources

Fresh qualification passed all eight multimodal input probes and four disposable
training hardware probes on each A100. Before rollout, each trained adapter passed
one largest/smallest paired-input probe per algorithm on each GPU, including
scalar/mixed/repeated semantics and base-adapter isolation. Both paired inputs
were checked. Historical logs display these probes as 1/2 because the denominator
counted candidate inputs; the later display fix counts primary probes and reports
the two qualified inputs separately. No experiment result or old log was rewritten.

GPUs 0 and 1 used MASTER_PORT 18675 and 18676, with one model worker per GPU.
The run used 32K context / 384 output tokens, the frozen processor and complete
text-image semantic projections. Source data, images, goal constraints and Search
Memory were reused; no task or fact was truncated to obtain a passing result.
Worker reports retain peak allocated/reserved memory and elapsed time. Detailed
measurements and probe coverage are in `completion-summary.json`.

The short duration reflects the small training/evaluation scope and early invalid
exits in failed episodes. It is not a throughput certificate for long successful
search or for the full-corpus matched experiment.

## Evidence

- Original run: `outputs/multimodal_development/issue76-feasibility-v1/attempt-001/`.
- `result.json`, `adjudicate.json`, `training.json`, `references.json`, `evaluation.json`.
- Per-worker qualification records, logs and final adapters under that run directory.
- Independent audit: `docs/experiments/issue76/completion-verification.json`.
- Resources and threshold failures: `docs/experiments/issue76/completion-summary.json`.
- Retained structured parent progress: `docs/experiments/issue76/parent-progress.jsonl`.

#77 must use this complete negative feasibility evidence for its go/no-go decision.
Closing #76 records executed and verified work; it does not claim a scientific
performance PASS, a matched visual/multimodal comparison, or downstream completion.
