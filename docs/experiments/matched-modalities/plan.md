# Matched modalities under a twelve-hour experiment budget

> Execution update: bounded candidate preparation reached a verified Storage
> resource stop. See [the preparation result and unfulfilled prerequisites](preparation-stop.md).
> The frozen protocol below remains unchanged. CPU preparation/verification and
> no-launch guards exist; final views and the full GPU runner/qualification do not.

Study: `matched-modalities-v1`. Status: **protocol fixed; implementation,
qualification, training and final evaluation pending**. This plan is the
user-requested successor to the completed deadline feasibility study. It does
not change any historical result, checkpoint, split, receipt or release.

## Question and scope

Under equal task-specific training exposure, how do text-state, visual-state
and multimodal-state observations affect full-episode invariant-valid search
success, invalid-operation charges and search cost on the same unseen tasks?
This is a small single-seed comparison, not a claim about general planning,
architecture generalization or intrinsic modality superiority.

Retain four settings: `bfs`, `best_first_width`, `best_first_add_w3` and
`best_first_add_greedy`. The latter two use h_add and differ in priority/reopening;
they are not the original h_max/landmark-count comparison. All three modalities
run every setting. Training membership is matched **within each algorithm
across modalities**, not between different algorithms' teacher traces.

Final evaluation has one new problem each in **storage, blocksworld and ferry**,
identical across all algorithms and modalities: three whole problems, twelve
algorithm/problem cases, twelve final SFT adapters. The entire small matrix is
fixed now. No further algorithm/domain reduction is allowed in this version;
failure to admit it within the budget produces a resource stop. This avoids
selecting algorithms according to the already observed #75/#76 scores.

## Existing evidence and boundaries

- #72: 238 task groups, 49,274 states and 76,217 decision bindings after the
  input-size-only whole-task exclusions. Both collect-003 and collect-004 remain
  necessary. Reuse existing scenes/pages/recipes; do not regenerate that corpus.
- #73/#74: released matched projections of those same authoritative records.
  Corpus release is not hardware qualification or experiment completion.
- #75: the completed two-epoch, 43,876-record visual run and its failed BFWS
  performance gate remain unchanged. It is not a matched checkpoint here.
- #76: the completed 512-record/one-epoch multimodal pilot remains negative
  development evidence. Its record selection and schedule inform this prospective
  design, but its adapter is not reused as a new primary-study run.
- #67: staged/shuffled/mixed-order curriculum controls completed with equivalent
  selected-panel success and saturated random-valid controls. Report separately;
  do not pool as a matched text baseline or claim a curriculum-by-modality effect.
- #77, #100 and #108: the old NO_GO, feasibility report and deadline-study-v1
  release stay completed historical artifacts. New evidence needs successor
  reporting/release work; this planning goal does not publish new results.

The design is informed by known development results; it is not retrospectively
preregistering #75/#76. No new final model outcomes have been observed for it.
DAgger (#78–#84), end-to-end (#85–#89/#99), broader robustness/generalization
(#96/#98), replication (#101–#103) and transfer (#104–#107) receive zero budget.

## Fixed training exposure

`configs/experiments/matched-modalities/membership.json` contains all ordered
record IDs, copied from the completed pilot's declared selection, plus explicit
source task/domain/split summaries. `study.json` records the numeric settings.
These files are protocol data, not inputs accepted by the old runners.

- Exactly 512 unique records per algorithm, once each, in the recorded order:
  one epoch, sequential sampler, no reshuffle, packing or length regrouping.
  Total: 2,048 semantic records and 6,144 modality presentations.
- Seed 17 for model initialization, data and training; a separate new adapter
  from the same base weights for each algorithm/modality. No warm start from
  historical SFT and no additional seeds or checkpoint selection.
- Microbatch one, accumulation 32, one GPU per adapter, effective batch 32,
  exactly 16 optimizer updates. The second GPU trains an independent adapter;
  it does not double that adapter's batch size.
- AdamW (`adamw_torch`), learning rate 1e-4, betas (0.9, 0.999), epsilon 1e-8,
  weight decay zero, max gradient norm one, cosine schedule, warmup ratio .03
  (ceil to one warmup update). Loss covers the identical assistant target only;
  prompt, image and padding positions are masked using the shared collator.
- LoRA rank 64, alpha 128, dropout .05, bias none, all-linear target modules
  excluding `.*visual.*`, CAUSAL_LM. Base and vision parameters frozen; bf16
  training with SDPA, non-reentrant gradient checkpointing, training KV cache off.
- Diagnostics use the fixed development IDs: BFS 28, BFWS 26, additive 27 each,
  at updates 5 and 10, plus final-adapter technical checks. No diagnostic-based
  early stopping, checkpoint selection, prompt tuning or extra training.

Training spans the source domains listed in membership.json. It is **not** a
three-domain training set. In particular there are zero Storage training rows
in these subsets, so Storage is outside the domain exposure of this task-specific
SFT, although it occurs in historical development and may occur in pretraining.
Do not call the whole final panel uniformly in-distribution or unseen-domain
transfer. Different source algorithms also have different training-domain mixtures;
algorithm comparisons do not isolate algorithm alone.

All selected training rows currently resolve to released train shards, diagnostics
to dev shards, with disjoint source task IDs. #92 must additionally validate the
semantic/input split boundary across all selected algorithms and the new tasks;
task-ID spelling (including historical `train` substrings in dev IDs) is not the
split authority. Any overlap is a technical failure, not permission to relabel it.

## Observation and processor contract

Use Qwen/Qwen3-VL-8B-Instruct and Qwen3VLProcessor at revision
`0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`, including its tokenizer/chat template
and image preprocessing defaults. No processor resizing override. Record actual
package versions in qualification and keep them fixed through execution.

Use the #74 shared semantic projection and existing family-specific builders.
Text carries full task context, source-goal constraints and current facts;
visual carries the #72 ordered task-context/current-state/goal page collection;
multimodal carries both. Preserve goal quantifiers, negation, scope, object names,
static facts, dynamic facts and fluents. All pages accompany every visual call.
The annotated visual baseline includes text drawn on images; it is not a claim
about learning solely from unlabelled natural images.

Keep 768x1024 annotation pages, DejaVuSans 24px, original 128x128 scenes and the
64 MiB per-process state-page cache. Reuse approved readability for unchanged
assets; inspect processed previews of newly generated views, including the
densest page. New task scenes must follow the accepted local supplied-plan ADR;
the renderer must never invoke a hosted planner.

Search Memory is identical across modalities: 32,768 serialized bytes maximum,
16 accepted deltas, same family schemas and exact candidate/visited/pruning facts.
It is not an extra 32K token allowance. Preserve the model-owned operation
boundary; no successor images before their producing operation and no silent
runtime repair. Existing rendering caches do not imply model memory.

The complete input, including template and memory, is at most **32,384 tokens**;
reserve **384 output tokens** within **32,768 total**. No fact/page/target
truncation or smaller fonts. Measure all training/diagnostic rows and final
reachable-state views plus complete live Search Memory inputs. An unforeseen
runtime overflow is a technical stop with retained evidence, not a model error.

## Final task selection and protocol (#90–#92)

Before training, #91 implements the fixed candidate recipe in study.json using
the existing local generator adapters and trusted PDDL normalization:

| Domain | Generator arguments before its seed/output arguments | Candidate seeds |
| --- | --- | --- |
| blocksworld | `4 4` (four operators, four blocks) | 730000–730063 |
| ferry | `-l 3 -c 2` | 740000–740063 |
| storage | `-p 01 -o 1 -c 2 -n 1 -s 4 -d 1` | 750000–750063 |

Use the adapters' actual seed/output conventions. Retain every candidate and
rejection reason. Within each domain, select the **first eligible seed**, not
the best model outcome. Eligibility requires: no normalized semantic task overlap
with any retained source training/development task or historical evaluated task;
non-goal initial state; exact trusted references succeed under all four settings;
at most 64 exact expansions and 128 exact decisions per setting; complete finite
reachable-state enumeration within 256 states; complete views fit the processor
contract. Bound each candidate's reference/enumeration work to 60 seconds.
Reject a candidate as a whole across modalities/algorithms. Exhausting all 64
seeds in any domain stops this version; do not invent another domain/profile.

#91 records PDDL and reference costs; #92 completes view/layout eligibility and
records the final three selected task IDs before any new trained model outcomes.
All reachable states need render/view coverage because student exploration can
leave the teacher trajectory. New final tasks require a separate manifest and
read-only runtime/view binding; never insert them into the old train/dev corpus
loader by relabelling the split. No final outcomes may influence data selection.

Final checkpoints are selected solely by completing update 16 and technical
verification. Inference is float32 with the existing `visual_sdpa` implementation
for every modality, greedy `do_sample=false`, 384 maximum new tokens, seed 17,
batch size at most two, padded batch input cost at most 24,000 tokens. Inputs
larger than that batching cap run singly if hardware-qualified and within 32K.
Use scalar/mixed/repeated-input and adapter-isolation checks on both GPUs.
No cross-episode output cache; only per-call KV caching. Stop on normal EOS.

Each algorithm/problem has the same exact-reference expansion allowance for
all conditions and modalities and a decision allowance of twice its exact
reference decision count. The runtime accepts algorithm-valid ties, charges
invalid operations and never supplies the correct replacement. Preserve the
existing deterministic-invalid-operation termination behavior. Budget exhaustion
is an unsuccessful observed episode, not incomplete experiment coverage.

Conditions are pretrained base, process SFT, random-valid and exact reference.
There are **144 logical episode bindings**: 3 modalities x 4 algorithms x
3 problems x 4 conditions. Base and SFT require 72 model episodes; exact and
random may share 24 physical reference episodes only when task, algorithm, seed,
budget and operation contract agree. Retain all 144 modality bindings even when
physical reference traces are shared. Use separate source-goal/view provenance.

Report per-algorithm paired modality differences, exact counts and each whole
problem's outcomes. The primary endpoint is invariant-valid episode success;
invalid-operation rate, budget exhaustion, decisions, expansions, solution cost,
tokens, model latency and memory are separate endpoints. Report all three
pairwise modality differences descriptively, without choosing a winner by a
significance threshold. If intervals are shown, use 10,000 whole-problem paired
bootstrap resamples, seed 1729, 95% percentile intervals; resample a problem's
entire algorithm/modality block together. Three problems cannot justify broad
significance or training-seed-variance claims. Report base/random/exact controls
including saturation, rather than interpreting success alone as learned advantage.

#109's secondary common cap is `min_a(2 * exact_decisions[a, task])` per problem,
applied only as observed-trajectory prefix accounting. If displayed budgets
affect policy behavior, label it descriptive prefix survival, not a counterfactual
rerun. Never infer missing continuations or run extra model episodes.

## Cumulative resource accounting and continuation

| Stage | Hard aggregate wall allowance | Includes |
| --- | ---: | --- |
| Qualification | 3,600 seconds | model load, timing/parity and disposable probes, failed attempts |
| Training/development | 18,000 seconds | all 12 adapters, loads, saves, diagnostics, adapter checks, failed attempts |
| Final evaluation | 21,600 seconds | all three modalities, loads, model episodes, failed attempts |

Total is **43,200 seconds / 12 hours**, not 12 hours per modality or attempt and
not GPU-hours. Within a stage count the union of active launch intervals across
both GPUs; intervals of separate attempts are accumulated, not reset on resume.
Do not overlap different stages. Also report actual GPU-hours separately where
measurable. Offline CPU preparation/replay/writing and idle operator time are
outside these GPU-stage caps and must be reported separately, not hidden in ETA.
No stage borrows unused time from another and no automatic extension is allowed.

The future runner must maintain a single persisted stage-budget ledger, refuse
duplicate live launches, recover elapsed time after interruption, and enforce
parent/worker deadlines, not merely stop new work at the next optimizer step.
Reserve 120 seconds per stage for shutdown; stop launching work at cap minus
120 seconds and terminate only this study's workers by the hard cap. Retain
partial outputs. A restart spends the remaining allocation; it is not a new seed.
Do not terminate unrelated GPU processes. Use at most one model worker per GPU;
explicit MASTER_PORT 18775 for GPU 0 and 18776 for GPU 1. If occupied, record an
alternative free port before launch. Qualify with the actual available VRAM.

Before new training, qualification must conservatively price all 12 training
cells and 72 final model episodes using declared reference call limits and
forced-384-output timing, including load/save/diagnostic overhead. Use the slowest
measured applicable probe with a 1.25 safety factor. Measure each modality on both
GPUs; do not reuse visual timing as a multimodal estimate. Keep the prescribed
two-worker schedule and its actual projected makespan. If any stage cannot fit
its remaining allowance, stop before starting it; no outcome-driven reduction.
Qualification itself is a future task, not accomplished by this protocol freeze.

The successor decision requires complete matching checkpoints, valid views and
runtime replay, passed technical qualification, and budget feasibility. It has
**no minimum learned success or maximum model-invalid-rate gate**. Even zero
model success is valid completed negative evidence when the complete matrix was
executed and independently checked. Historical 80%/5% gates stay historical.

Keep execution completeness, technical validity and measured performance as
separate fields. Preserve governed PASS/VALID_STOP/INVALID/ANCESTOR_STOP meanings:
resource stops are VALID_STOP with missing work explicit; provenance/replay/input
failures are INVALID; downstream work blocked by a technical predecessor records
ANCESTOR_STOP. A complete negative comparison can pass its technical acceptance
criteria without asserting improved competence. A partial matrix must not be
called a completed matched experiment. A terminal stop report completes only its
reporting obligation, not unfulfilled training/evaluation acceptance criteria.

## Tickets and executable handoffs

Issue bodies' `Blocked by` sections and `ticket-map.json` record the same direct
dependencies. Historical closed tickets are evidence links, not failed live gates.
No separate human-approval manifest is required by this successor plan. The
current goal authorizes planning and tracker edits only, not GPU experiments.

| Ticket | Deliverable and acceptance | Direct prerequisites |
| --- | --- | --- |
| #90 | Fixed protocol, membership/settings and synchronized issue map | #38 scope amendment |
| #91 | Candidate PDDL, disjointness checks, reference costs and bounded enumeration | #90 |
| #92 | Matched training projection, final selected views, runner, tests/dry-run and hardware qualification | #91, #72, #73, #74 |
| #112 | Four fresh text adapters, exact schedule/coverage, diagnostics and verification | #92 |
| #113 | Four fresh matched visual adapters; successor to #75 | #92 |
| #114 | Four fresh matched multimodal adapters; successor to #76 | #92 |
| #115 | CPU comparability/technical continuation decision; successor to #77 | #112, #113, #114 |
| #93 | Final text episodes and independent replay; no training | #115, #112 |
| #94 | Final visual episodes and independent replay; no training | #115, #113 |
| #95 | Final multimodal episodes and independent replay; no training | #115, #114 |
| #97 | Trace-derived validity/process diagnostics, all failures and missingness | #93, #94, #95 |
| #109 | Primary budgets and bounded common-cap prefix accounting | #90, #93, #94, #95 |

Training tickets are logically independent but share one five-hour allocation
and scheduler; do not launch three separate two-GPU runners. Execute modalities
in text, visual, multimodal order, algorithms in the fixed order above, assigning
the next algorithm to the next free worker with stable tie-breaking GPU 0 first.
Final modality jobs execute #93 then #94 then #95 within the shared six hours.
After a technical stop, CPU analysis can record available evidence and missing
cells without waiting for unperformed experimental tickets to be closed complete.

## Commands to implement (not available yet)

Extend the existing family/runtime/projection seams; do not silently run
`run_visual_issue75.py all` or `run_multimodal_issue76.py all` with old defaults.
#91 first implements `scripts/prepare_matched_final_tasks.py` for CPU-only
candidate generation/reference/enumeration, writing
`outputs/matched_modalities/v1/preparation/candidates.json`. It must support
`--study`, `--workers` and `--dry-run`, with no GPU calls. This independent
candidate-pool handoff lets #91 finish before #92 implements view selection.

The intended common CLI is `scripts/run_matched_modalities.py`, with the following
command contract. It does not exist at this planning checkpoint:

```bash
source ~/cd_vlaplan
python -u scripts/prepare_matched_final_tasks.py --study configs/experiments/matched-modalities/study.json --workers 4 --dry-run
python -u scripts/prepare_matched_final_tasks.py --study configs/experiments/matched-modalities/study.json --workers 4
python -u scripts/run_matched_modalities.py prepare --study configs/experiments/matched-modalities/study.json --workers 4 --dry-run
python -u scripts/run_matched_modalities.py prepare --study configs/experiments/matched-modalities/study.json --workers 4
python -u scripts/run_matched_modalities.py qualify --study configs/experiments/matched-modalities/study.json --devices 0 1 --master-ports 18775 18776
python -u scripts/run_matched_modalities.py train --study configs/experiments/matched-modalities/study.json --devices 0 1 --master-ports 18775 18776
python -u scripts/run_matched_modalities.py decide --study configs/experiments/matched-modalities/study.json
python -u scripts/run_matched_modalities.py evaluate --study configs/experiments/matched-modalities/study.json --modality text-state --devices 0 1 --master-ports 18775 18776
python -u scripts/run_matched_modalities.py evaluate --study configs/experiments/matched-modalities/study.json --modality visual-state --devices 0 1 --master-ports 18775 18776
python -u scripts/run_matched_modalities.py evaluate --study configs/experiments/matched-modalities/study.json --modality multimodal-state --devices 0 1 --master-ports 18775 18776
python -u scripts/run_matched_modalities.py verify --study configs/experiments/matched-modalities/study.json --workers 4
```

Every mode needs `--dry-run` with no output mutation, model calls or worker
launches. `train`/`evaluate` need `--resume` preserving schedule and cumulative
budget; `verify` is read-only and rejects false complete coverage. Every mode
reports stage, completed/total, elapsed and ETA, with heartbeats at most 30 seconds
apart during long work. The final summary names pending work and exact evidence
paths. Long runs are not performed in this goal.

#92's focused tests must exercise semantic parity/no future images, split
isolation, identical membership/order/batch/update counts, no historical-checkpoint
substitution, deadline accounting across resume/concurrent workers, partial
coverage refusal, negative-results continuation, and full episode replay. Include
a real CPU dry-run and bounded GPU smoke/qualification within its one-hour cap.
Never count a command specification as tested runnable implementation.

## Completion of this planning goal

Verify that all 2,048 training and 108 diagnostic IDs resolve uniquely to the
retained release, verify ordering/counts and source splits, inspect the numeric
protocol and dependencies, and read back the revised GitHub bodies/states.
Commit and push the plan/configuration/ticket map and verification evidence.
#90 may close as a completed protocol ticket; all implementation/experiment
tickets remain pending. This goal makes no GPU qualification, training, final
evaluation, manuscript or new artifact-release completion claim.
