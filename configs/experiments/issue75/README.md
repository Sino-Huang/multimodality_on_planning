# Visual development matrix (#75)

The runner performs visual-state qualification, references, training, rollout and
adjudication. Run it directly; no authorization or approval file is required.
The previous attempts remain preserved: v1 stopped at its qualification time
limit; v2 ran out of GPU memory at batch size eight. V3 passed hardware
qualification on both GPUs, then stopped at a conservative runtime estimate.
None trained or evaluated a policy. V4 reuses that passed hardware qualification
and makes runtime estimates advisory by default.

## Run

```bash
source ~/cd_vlaplan
python scripts/run_visual_issue75.py all --dry-run
python -u scripts/run_visual_issue75.py all
```

The current configuration writes to a fresh directory:
`outputs/visual_development/issue75-32k-v4/attempt-001`.
Dry-run checks the reusable qualification and prints child commands without
writing experiment outputs or making model calls. The current run reuses v3
qualification; it does not repeat the 76-minute GPU qualification stage.

For another fresh run, choose a new output directory:

```bash
python -u scripts/run_visual_issue75.py all \
  --output outputs/visual_development/issue75-32k-v4/attempt-002
```

For an interrupted run that has no final `result.json`, use the same directory
and `--resume`. Resume retains its settings and original monotonic clock,
including downtime; it replays completed episodes and resumes training from the
latest checkpoint. A completed result is preserved; use a new directory to rerun.
Settings are ordinary JSON in `experiment.json`. Each run records a snapshot of
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

`budget_mode: "advisory"` is now the default. It keeps the full development
panel, prints both stress projections and does not reject or interrupt a run
based on elapsed time. Per-episode call/expansion limits, context/memory limits,
complete-coverage checks and semantic validation remain enforced. This fixes
an estimate-based stop; it does not speed up training or establish that the
experiment will fit within 20 hours. The actual run may be lengthy.

For a strict budget, set `budget_mode` to `"hard"` in `experiment.json`. This
retains the full-then-cost-fallback selection and enforces the configured
`gate_seconds` (20 hours), `stop_new_calls_seconds` (18 hours) and
`rollout_certification_seconds` (15 hours). Use a fresh output directory when
changing settings.

`qualification_source` points to v3's `qualification.json`. Reuse checks the
saved model, data, training and device settings and requires complete passed
probe records from both workers. Their original contract IDs are preserved in
the new report. Budget and output changes need no new GPU qualification. If you
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

The stages are qualification, cost-only panel selection, references, training,
model evaluation and independent replay/adjudication. In hard-budget mode, if the full dev workload
cannot fit, selection tries the predeclared cheapest complete task per
domain/family (42 task groups), keeping additive settings paired. Advisory mode
keeps the full panel. Selection never
uses model success and retains the complete training set. Later matched
modalities must use the same selected panel for a comparison.

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
