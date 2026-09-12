# Visual development experiments (#75)

## Completed v5 experiment

The operator continued the older v5 run instead of switching to the pilot. All
four full-corpus adapters and all 864 selected episodes completed in **76.23 hours**.
Its outcome is `VALID_STOP`, with `complete_selected_coverage: true`: BFWS success
was 66.7%, below the frozen 80% threshold. This is complete experimental evidence
with a failed performance gate, not a runtime failure. Original receipts remain
unchanged. See the [v5 completion report](../../../docs/experiments/issue75/v5-completion.md).

The four-hour pilot below was **not run** and is not required to close the completed
v5 execution. Do not rerun #75 just to turn its outcome into PASS. Before #76 or
later modality comparisons, reconcile training scope: v5 used 43,876 records and
two epochs, so its adapters are not matched to 512-record/one-epoch pilot adapters.
No longer downstream experiment is implicitly authorized by this completed run.

## Optional pilot configuration

The default command now runs a **four-hour deadline pilot** from
[`pilot.json`](pilot.json), with exact sample membership in
[`pilot-plan-v1.json`](pilot-plan-v1.json). It uses seed 17 for training and
evaluation, 512 complete training records per algorithm, one epoch (16 optimizer
updates), and at most 32 teacher-diagnostic records per algorithm. Training is
balanced across available domains within a 4,096-token visual-input cap, then
ordered easy to hard; the four algorithms receive their own source records.
Later modalities must reuse those exact record IDs.

Evaluation retains storage, blocksworld and ferry: 12 algorithm/task cases and
48 episodes across base, SFT, random-valid and exact-reference controls. Selection
uses reference cost and input size before model outcomes. All facts and goal
constraints remain complete. These small, inexpensive cases support a feasibility
study; they do not establish broad planning generalization or seed variance.

The runner stops launching calls after 3 hours 45 minutes and terminates its own
workers at four hours. It does not stop unrelated GPU processes. A timeout saves
partial evidence and cannot count as a complete pilot. Completed negative evidence
can proceed to #77 without repeated training. Pilot results always state
`full_matrix_complete: false`; `pilot_complete` requires complete replayed coverage.
The input-weighted evaluation proxy is about 1.8 hours, not a measured ETA;
training, adapter qualification and I/O also consume the four-hour budget.

The previous full-size configuration remains in `experiment.json` for historical
reproduction and is **not the CLI default**. An already-running full-size process
is unaffected by this change. Do not start this two-GPU pilot alongside that run.
See the [deadline roadmap](../../../docs/experiments/deadline-plan/README.md) for
matched-modality scope and the revised ticket ordering. No approval file is needed.

## Run

```bash
source ~/cd_vlaplan
python scripts/run_visual_issue75.py all --dry-run
python -u scripts/run_visual_issue75.py all
```

The current configuration writes to a fresh directory:
`outputs/visual_development/issue75-deadline-pilot-v1/attempt-001`.
Dry-run checks the reusable qualification and prints child commands without
writing experiment outputs or making model calls. The current run reuses v3
qualification; it does not repeat the 76-minute GPU qualification stage.

For another fresh run, choose a new output directory:

```bash
python -u scripts/run_visual_issue75.py all \
  --output outputs/visual_development/issue75-deadline-pilot-v1/attempt-002
```

For an interrupted run that has no final `result.json`, use the same directory
and `--resume`. Resume retains its settings and original monotonic clock,
including downtime; it replays completed episodes and resumes training from the
latest checkpoint. A completed result is preserved; use a new directory to rerun.
Pilot settings are ordinary JSON in `pilot.json`. Each run records a snapshot of
those settings. Changing them does not require a matching approval document.

The runner uses GPUs **0 and 1**, one model process per GPU, with distinct
`MASTER_PORT` values **18575 and 18576**. Four localhost renderer ports are
**18092–18095**. If the renderer is not running, start it in another terminal:

```bash
source ~/cd_vlaplan
.cache/issue70-backend-venv/bin/python scripts/serve_issue70_planimation.py \
  --port 18092 --workers 4
```

Worker output is streamed to the terminal and saved in
`launches/<stage>/worker-*.log`. Progress includes completed/total, elapsed time
and ETA; **20-second heartbeats** retain the latest activity and progress.
Qualification logs each scalar, mixed batch, repeated batch and timing operation.
Completed probe measurements are saved under
`qualification/worker-<n>-probes/` even if a later probe stops. These partial
measurements do not count as complete qualification.

## Historical full-size evaluation panel

The following sections explain the prior full-size configurations and their
failures. To reproduce that longer scope explicitly, pass
`--config configs/experiments/issue75/experiment.json`; it has no live time cap
and is outside the deadline plan.

That configuration's `cost_panel` is
[`cost-panel-v1.json`](cost-panel-v1.json). It retains **42 of 97 dev task groups**
and excludes **55**. The retained scope has **54 algorithm/task cases and 864
condition episodes**: 15 BFS, 15 BFWS, 12 additive w3 and 12 additive greedy cases.
Every available domain/algorithm-family combination remains represented.

Costs use each reference decision's complete visual input-token count and its
algorithm's measured timing curve. Each curve uses the slower GPU measurement,
an upper-neighbour lookup and a monotone envelope. Inputs above the largest
calibration point use proportional extrapolation. This avoids charging short
inputs the global 93-second maximum. Costs still use full 384-token generations
and maximum episode call allowances, so they are **proxies, not ETAs**.

Task contexts identify shared problems across algorithms. Those groups, including
all additive w3/greedy pairs, are selected or removed together. Selection first
keeps the cheapest groups needed for domain/family coverage, then adds affordable
groups in cost order. Text, visual and multimodal comparisons must use the same
saved task membership through `panel_task_ids`; only visual hardware timing has
been measured. No learned outputs or model success scores drive selection.

| Evaluation quantity | Full | Selected |
| --- | ---: | ---: |
| Dev task groups | 97 | 42 |
| Algorithm/task cases | 120 | 54 |
| Condition episodes | 1,920 | 864 |
| Input-weighted cost proxy, two GPUs with margin | 129.4 days | 19.4 days |

Pruning removes about **85% of the evaluation work proxy**. The coverage-preserving
base already exceeds the 15-hour evaluation target under these assumptions;
`fits_evaluation_budget` is explicitly false. No domain or algorithm is silently
dropped to make that flag pass. This does not establish a 20-hour end-to-end run.

The **43,876 training records remain unchanged**, as do the two teacher-loss
passes over the full dev set. Their costs are reported separately. The retained
hardware data has only a maximum training-microstep time, so its combined
training/diagnostic stress projection is about **11.25 days**; no representative
short-input training ETA is claimed. Evaluation pruning does not eliminate this
fixed training work.

Rebuild or inspect the panel without model calls:

```bash
source ~/cd_vlaplan
python scripts/prepare_visual_cost_panel.py --dry-run
python scripts/prepare_visual_cost_panel.py --evaluation-hours 15
```

The manifest records every candidate's input-size statistics, reference counts,
rank, cost, selected/excluded reason, calibration sources and shared problem
membership. The runner snapshots it into `attempt.json` and rejects panel changes
on resume. Use a fresh output directory after changing the panel. Qualification,
reference runs, rollout and adjudication enforce the selected IDs; GPU task
assignment uses the same cost-weighted placement as the estimate. The #74 corpus,
its original splits, images and records are not rewritten. The deadline pilot manifest now defines the
smaller handoff to #76; neither manifest is evidence that #76 is complete.

## Qualification timeout fix

The original code scheduled **940 generation calls per GPU**: it tested three
modalities for this visual-only matrix and repeatedly generated scalar outputs
for identical entries in mixed batches. Model loading took about a minute,
whereas each of the first four complete probes took roughly 11–16 minutes.
A separate one-hour cutoff stopped the run after 4 of 31 probes.

The v2 visual qualification reduced this to **151 generation calls per GPU**,
an 84% reduction in calls, keeping all 31 selected probe records. It computes one
scalar result for each distinct input and compares every position in both the
mixed batch and repeated batch against that result. It retains full 384-token
generation timing, actual processor/context checks and the training hardware
probe. Trained-adapter qualification uses the same distinct-input comparison and
still checks base/adapter isolation. This does not cache scientific rollout
outputs. Text and multimodal generation qualification belongs to those runs;
this visual run does not certify them.

V3 completed all 31 probes plus the training hardware probes on both GPUs in
about 76 minutes. Those reports are retained under
`outputs/visual_development/issue75-32k-v3/attempt-001/qualification/`.

## Runtime estimates and qualification reuse

V3's hardware qualification passed. Its next step projected the entire workload
using the slowest forced-384-token generation (93.0 seconds per logical call),
the slowest training microstep (12.0 seconds), maximum episode call allowances,
and a 1.2 margin. This produced stress projections of about **431 days** for
full coverage and **76 days** for the fallback. Neither fit a hard 20-hour budget.
These are not measured ETAs: they apply the largest-input cost to every example,
charge backward/optimizer work even to diagnostics, and assume all episodes
exhaust their call budgets. They also omit separately timed references, adapter
checks and I/O, so they are not guaranteed wall-time bounds either.

`budget_mode: "advisory"` remains in the historical full-size configuration. It uses the configured shared
cost panel, prints the cost projections and does not reject or interrupt a run
based on elapsed time. Per-episode call/expansion limits, context/memory limits,
complete-coverage checks and semantic validation remain enforced. This fixes
an estimate-based stop; it does not speed up training or establish that the
experiment will fit within 20 hours. The actual run may be lengthy.

For a strict budget, set `budget_mode` to `"hard"` in `experiment.json`. This
enforces the configured panel against the time limits in
`gate_seconds` (20 hours), `stop_new_calls_seconds` (18 hours) and
`rollout_certification_seconds` (15 hours). Use a fresh output directory when
changing settings.

`qualification_source` points to v3's `qualification.json`. Reuse checks the
saved model, data, training and device settings and requires complete passed
probe records from both workers. Their original contract IDs are preserved in
the new report. Budget, output and evaluation-panel changes need no new GPU qualification. If you
change an execution setting such as batch size or attention backend, set
`qualification_source` to `null` and run fresh qualification. An incomplete or
failed hardware qualification is never bypassed by advisory mode.

## GPU memory fix

Each GPU runs its own model copy; the two 80 GB cards do not form one shared
160 GB memory pool. The float32 backbone alone allocates about 32.7 GiB on each
card. Batch activations, image processing and generation caches need additional
space. The v2 batch of eight ran out of memory with another process using
9.31 GiB on GPU 0. The other process remains running.

The largest selected input also failed at batch size one: the installed
float32 grouped-query SDPA path requested a **33.63 GiB attention matrix**.
The `visual_sdpa` inference backend expands key/value heads explicitly and uses
PyTorch's memory-efficient kernel, avoiding that quadratic math-kernel fallback.
It reuses Transformers' causal and padding mask builder. Model precision stays
float32, and training keeps its existing bf16 attention configuration.

V3 also reduces inference batches from eight to two and the padded batch-token ceiling
from 48,000 to 24,000. This affects qualification, trained-adapter checks and
rollout together. All tasks, complete observations, model precision, output-token
allowances and the training global batch remain unchanged. The largest visual
inputs are now qualified first. Each completed probe records peak allocated,
peak reserved and remaining GPU memory alongside its timings.

A bounded live GPU check reproduced the old batch-eight OOM in a fresh worker.
The same input at batch two completed all 384 output tokens with **41.4 GiB**
peak PyTorch allocation, while the other process stayed running. With efficient
attention, the largest selected probe (16,795 input tokens) also completed all
384 output tokens at **41.9 GiB** peak allocation on GPU 0. See
`docs/experiments/issue75/memory-fix.json` for retained measurements. The attention
registration follows the [Transformers attention interface](https://huggingface.co/docs/transformers/attention_interface),
including its required mask registration. These bounded
checks do not replace full qualification or establish matrix completion.

## Data and execution

The input is the complete #74 matched corpus. All #72/#73 state/goal pages,
source splits, teacher targets and bounded Search Memory remain unchanged.
Each observation attaches its complete context, current-state and partial-goal
pages. Existing scenes are referenced directly. Newly accepted states outside
the expert catalog are rendered from their supplied Action Sequence through
localhost Planimation, after the producing operation. Replay never renders a
missing image. The state-page cache is shared and bounded to 64 MiB per process.

The four algorithms are BFS, BFWS, additive w3 and additive greedy. The full dev
scope contains **97 task groups / 120 algorithm episodes / 1,920 condition
episodes**, covering exact reference, random-valid, pretrained base and process
SFT. Evaluation seeds are 17, 29, 43, 71 and 101. Each algorithm trains exactly
one seed-17 adapter; these are not independent training-seed replicates.

| Algorithm | Training rows | Optimizer steps |
| --- | ---: | ---: |
| BFS | 11,911 | 746 |
| BFWS | 14,225 | 890 |
| Additive w3 | 9,398 | 588 |
| Additive greedy | 8,342 | 522 |

Training uses two epochs, bf16, SDPA, global batch 32 and language-model LoRA
rank 64 (alpha 128, dropout 0.05), with the vision backbone frozen. Only assistant
teacher targets receive loss. One-third and two-thirds checkpoints receive
teacher-forced dev-loss diagnostics; only the final adapter is evaluated in
rollout. Inference uses float32, 32,768 context tokens with 384 reserved for
output, and batches of at most **two requests / 24,000 padded input tokens**.

The stages are qualification, panel binding, references, training, model
evaluation and independent replay/adjudication. The configured cost panel is used
in both advisory and hard-budget modes; hard mode can reject it when it exceeds
the configured limits. Without a cost panel, the older full/fallback selection
is still available. Later matched modalities must consume the same saved panel
for a valid comparison.

Every episode has twice its exact-reference decision-call allowance and a
separate expansion limit. Deterministic rounds issue at most one request per
active episode. Invalid operations are charged and never repaired. BFS accepts
valid FIFO ties; BFWS preserves the teacher corpus's explicit empty novelty
partitions. Completed episodes are retained immediately and independently
replayed. Partial coverage cannot pass adjudication.

## Results

Read `<output>/result.json` for the final outcome. `PASS` requires complete
selected coverage and the configured competence thresholds: exact success 1.0,
learned success at least 0.8 and learned invalid-operation rate at most 0.05 in
each setting. Learned-versus-best-control gain and paired whole-instance
bootstrap bounds are reported separately; panel success alone is not an
advantage claim.

`VALID_STOP` records a resource or threshold stop; `ANCESTOR_STOP` records a
stopped prerequisite; `INVALID` records a configuration, semantic or execution
error. None implies a completed successful matrix. There are no approval
receipts in new runs. The old attempt's receipts and source data are preserved
as historical evidence. Keep #75 open until actual execution is adjudicated.
