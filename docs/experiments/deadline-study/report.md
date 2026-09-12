# Deadline study: development feasibility and limitations

The study follows **#76 → #77 → #100 → #108**, taking the declared stop branch.
No final-test evaluation or DAgger intervention was run. The completed visual
experiment provides selected-panel evidence of executable typed-operation behavior;
the much shorter multimodal pilot fails its readiness thresholds. Their unequal
training schedules prevent a controlled modality-effect conclusion.

## Method and observed scope

The Search Process Policy is a pinned Qwen3-VL-8B-Instruct backbone with a separate
LoRA adapter for BFS, BFWS, additive w3 and additive greedy. It emits Typed Search
Operations into the Trusted Search Runtime. Search Memory, exact successor/candidate
information and bounded episode budgets are supplied externally. Validity checks
are mechanical; rejected operations are charged, retained and never silently repaired.
These experiments do not demonstrate an internal unbounded planner.

Visual-state inputs include an illustrative 128×128 scene and readable annotation
pages containing complete relational facts and partial-goal constraints. They are
an annotated-visual baseline, not an unlabelled-scene perception test. Multimodal-state
adds the same text-state facts and constraints. Pages use the existing shared
semantic projection and complete state/goal bindings, with no future images attached
before the producing operation. The source corpora, whole-instance splits, three
approved exclusions and on-demand view assets remain unchanged.

Both core experiments used training seed 17, frozen vision parameters, LoRA rank
64 / alpha 128 / dropout 0.05, global batch 32 and learning rate 1e-4. Training used
bf16; inference used the qualified float32 efficient-attention path, at most two
requests per batch, a 32,768-token context and 384 output tokens. Each GPU held its
own backbone and adapters. The available two A100s were used without overlapping
another experiment stage. Source configs retain all remaining optimizer settings.

| Scope | Visual #75 v5 | Multimodal #76 |
| --- | --- | --- |
| Training records | 43,876 across four algorithms | 512 per algorithm; 2,048 total |
| Epochs | 2 | 1 |
| Optimizer updates | 746 / 890 / 588 / 522 | 16 per algorithm |
| Evaluation task groups / algorithm-task cases | 42 / 54 | 9 / 12 |
| Evaluation seeds | 17, 29, 43, 71, 101; exact once | 17 |
| Episodes | 864 | 48 |
| Complete execution and independent replay | Yes | Yes |
| Frozen performance outcome | VALID_STOP | VALID_STOP |
| Recorded wall time | 76.23 hours | 64.92 minutes |

#76 covers storage, blocksworld and ferry. Its task IDs come from the existing
cost-selected panel; the full visual scope is recorded by ID in its frozen panel.
Selections used reference cost and layout constraints, not learned outcomes.
The four-hour visual pilot was prepared but never executed: the operator continued
the older full-size v5 run. No new visual training was added during this automation.

## Results on each experiment's own development panel

### Visual #75 v5

| Algorithm | SFT success | Random-valid success | Base success | SFT invalid-operation rate |
| --- | ---: | ---: | ---: | ---: |
| BFS | 75/75 | 53/75 | 0/75 | 0% |
| BFWS | 50/75 | 39/75 | 0/75 | 0.443% |
| Additive w3 | 60/60 | 60/60 | 0/60 | 0% |
| Additive greedy | 60/60 | 60/60 | 0/60 | 0% |

Exact references succeed in 54/54 cases. BFWS success is 66.7%, below the frozen
80% threshold; its gap to exact reference is 33.3 percentage points. The other
learned settings have zero success gap to exact reference on their selected cases.
The saved whole-problem bootstrap lower bound on gain over the best control is
+14.7 points for BFS, -14.7 for BFWS and zero for both additive settings. Only BFS
has a positive bound on this selected development panel. Additive random-valid
controls saturate, so 100% SFT success there does not establish a learned advantage.

### Multimodal #76

| Algorithm | SFT success | Random-valid success | Base success | SFT invalid-operation rate |
| --- | ---: | ---: | ---: | ---: |
| BFS | 0/3 | 1/3 | 0/3 | 42.86% |
| BFWS | 0/3 | 2/3 | 0/3 | 100% |
| Additive w3 | 1/3 | 3/3 | 0/3 | 18.18% |
| Additive greedy | 1/3 | 3/3 | 0/3 | 20% |

Exact references succeed in 12/12 cases. SFT succeeds in 2/12; ten learned episodes
terminate on deterministic invalid operations. Its success gaps to exact reference
are 100 points for BFS/BFWS and 66.7 for each additive setting. All four learned
settings fail both the existing 80% success and 5% maximum invalid-operation-rate
thresholds. Some generated outputs are valid JSON but contain incorrect operation
fields or state/update choices; syntactic validity is not runtime validity.

Base invalid-operation rate is 100% in both experiments. Random-valid is an
oracle-assisted programmatic valid-operation reference, not an equally trained
learned baseline. These comparisons include instruction/output-format compliance.
The low budget usage of quickly failing model episodes must not be interpreted as
efficient successful search. Exact references use half the available call allowance
because model episodes receive a 2× matching-reference call limit; expansion limits
are also enforced. Per-condition decisions, allowances, invalid counts, budget usage
and termination counts are retained in [core-results.csv](core-results.csv).

## Decision and limits

The [#77 decision](../issue77/decision.md) is **NO_GO**. The short multimodal regime
did not produce ready adapters for the proposed final comparison. A one-cell,
one-iteration DAgger branch would leave the other readiness failures and training
mismatch unresolved, so no optional cell was selected. The study stops further GPU
spending instead of changing thresholds or repeating training until positive.

This does not establish intrinsic multimodal inferiority. Training amount, schedule,
input length and evaluation scope differ between #75 and #76. More training is a
possible explanation for the difference, not an identified causal result. #67's
text/curriculum evidence uses another input/corpus and training contract and cannot
serve as a matched text baseline. The short pilot has only three problems per
algorithm and one evaluation seed; uncertainty is descriptive. The visual run's
five rollout seeds are not independent training replicates. No new training-seed
variance, held-out generalization, DAgger benefit, end-to-end successor-prediction,
backbone replication or transfer claim is supported.

The selected evidence supports the narrower finding that a trusted runtime can
validate complete multimodal search episodes and expose failures, and that the
longer visual training produced strong selected-panel adherence in several cells.
It does not establish the original broad cross-modality research claim. Additional
claims require a new prospective protocol and budget, not relabelling these results.

## Resource accounting

The original 16-hour proposal was not met by the earlier visual execution: #75 v5
alone took 76.23 hours. This automation ran #76 for 3,894.99 seconds within its
14,400-second cap, then stopped GPU work. Unused final-evaluation and optional
DAgger budgets were not reassigned. Current #76 worker reports show a maximum
recorded training allocation of 31.86 GiB and evaluation allocation of 41.45 GiB.
These are per-process PyTorch measurements, not total board memory or GPU-hours.
Whole-run v5 peak memory was not recorded; its qualification memory is calibration
evidence only.

| Retained core attempt | Outcome and interpretation | Wall time |
| --- | --- | ---: |
| #75 v1 | Qualification cutoff; no learned comparison | 3,609.47 s |
| #75 v2 | CUDA OOM during qualification; no learned comparison | 2,979.96 s |
| #75 v3 | Hardware qualification passed; clock projection rejected admission | 4,580.65 s |
| #75 v5 | Complete selected experiment; BFWS success gate failed | 274,431.03 s |
| #76 | Complete short experiment; all learned readiness gates failed | 3,894.99 s |

These timed core attempts sum to **80.42 wall-clock hours**. This is not the total
cost of the historical research program and is not GPU-hours. Earlier BFS/curriculum
training, data preparation and CPU audits/packaging are excluded from that sum;
complete historical totals are unavailable. [compute-accounting.json](compute-accounting.json)
records measured values, units, exclusions and missing measurements. The short
pilot's runtime reflects both its smaller scope and early invalid exits; it does
not certify throughput for a long successful search matrix.

## Historical evidence kept distinct

- **#54 v3:** live/training input mismatch and over-budget targets make those older
  results unsuitable as a clean efficacy baseline. Later repairs must not be
  retroactively attributed to that run.
- **#54 v6:** the corrected observable corpus exposed static context, exact candidates
  and visited membership, with corrected overlap/conflict audits. Training completed,
  but the broad checkpoint evaluation was interrupted for time cost; its partial
  roots are not a completed adjudication.
- **#54 v7 resource admission:** the original qualification receipt is not available
  in the retained inventory. A separately labelled CPU reconstruction using the
  retained v8 calibration and v7 rules rejects both 45-task full coverage (185.97 h
  projected) and the cyclic 15-task fallback (65.32 h projected) against the 15-hour
  rollout certificate. These are admission projections, not measured runtimes or
  a replacement original receipt. See [the reconstruction](bfs-v7-admission-reconstruction.json).
- **#54 v8:** complete, independently replayed cost-qualified evaluation on 15 tasks
  (11 easy, 3 medium, 1 hard), using the retained final v6 checkpoints. Learned and
  random-valid success both reach 100%, giving zero gain and a clean VALID_STOP.
  Its gate elapsed time is 28,465.57 seconds; that excludes the earlier v6 training.
- **#67:** 312 retained episodes support practical equivalence of staged, shuffled
  and mixed-order curricula on its selected panel. Each learned curriculum and
  random-valid reaches 100%; base reaches 0%. The original h-max/landmark-count
  heuristic-representation question remains ANCESTOR_STOP. Both replacement settings
  use h_add, so their comparison does not establish a heuristic-representation effect.

Source reports and scope limitations are collected in [prior-evidence.json](prior-evidence.json).
Historical multi-seed/curriculum runs are context, not pooled with the one-training-seed
core modality results. No historical outcome or receipt was rewritten.

## Artifacts and reproduction

The [published #108 release](https://github.com/Sino-Huang/multimodality_on_planning/releases/tag/deadline-study-v1)
contains source configs, exact training/task IDs, eight final adapters, original
receipts/logs, retained episode evidence, selected replay assets/tools and this
limited conclusion. All **912 episodes** were independently replayed from a
separately restored package with matching point metrics and zero model calls.
The package lists 8,305 replay assets and separate final adapter files; base Qwen
weights are not distributed.

This is a retained **evaluation replay** release, not a mirror of all training-corpus
assets. Full retraining requires the separately retained #72/#73/#74 resources.
Package versions, model/code revisions and reproduction commands are recorded in
the release index and [release tooling guide](release-tools.md). The completion
ledger and publication verification distinguish delivered artifacts from scientific
gate success.

#90–#95, #97 and #109 were not selected after NO_GO and are closed as not planned.
#78–#84 are likewise skipped optional work. #85–#89, #96, #98–#99 and #101–#107
remain deferred/open and unmeasured. This report is development feasibility and
limitations evidence, not a final-test paper result or completion of the parent
research program. No original performance outcome was rewritten.
