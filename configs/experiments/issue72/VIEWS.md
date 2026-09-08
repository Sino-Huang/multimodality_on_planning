# Readable state and partial-goal views (#72)

The user has since authorized a 32K whole-task filter. Current successor
instructions are in [VIEWS32K.md](VIEWS32K.md). The v1 evidence and workflow
below remain the record of the original 241-task contract.

The successor implementation is `issue-72-readable-pages-v1`. It is **not activated**.
The bounded dense Visitall qualification returned `VALID_STOP`: 49,963 input
tokens, exceeding 32,768 even before reserving 384 output tokens. Do not
materialize, close #72, or start #73/#74 releases or training from these results.
A complete qualification can map the remaining failures; the current evidence
already rules out activation under this contract's context ceiling.

The full layout-only dry-run covered 241 tasks, 51,208 states and 78,230
decisions in 35.65 seconds with four workers. No images or model calls were made.
Bounded processor runs covered Hanoi, Snake, Sokoban, 15-puzzle and a dense
Visitall task. These are development evidence, not full processor qualification
or human readability approval. See `docs/experiments/issue72/views-development.json`.

## Contract and storage

Pages are 768×1024 RGB PNGs with 24px DejaVuSans text. Ordered roles are
`task-context`, `current-state`, `goal`. The complete collection is attached on
**every** call. Text and drawings share semantic blocks. Facts group by section
and predicate, keeping complete fact strings and ordered arguments. Measured
wrapping splits long names without deleting characters. Continuations repeat
the block heading and retain exact offsets into its text.

Context includes original object/type declarations, static facts, and the
complete initial dynamic state/fluents. State pages show all current atoms and
fluents; the first includes the existing 128×128 illustrative scene at its
original size. Goal blocks carry ALL/ANY/NOT/FOR EVERY/THERE EXISTS labels and
explicit parent scope IDs. Source goals are parsed from original problem PDDL
before normalization. Normalized compiler goals remain execution metadata.
There are no solved scenes or state-dependent goal satisfaction indicators.

`collect-003` and `collect-004` must both remain available. No scene is copied.
Only reusable context/goal PNGs, compressed drawing recipes and decision
bindings are materialized. Current-state pages are composed on demand, with a
64 MiB per-process LRU keyed by task/state/page identifiers. Qualification
previews are retained separately. There is no total-disk cap and no hash,
checksum or scene-regeneration comparison.

## Commands

Use the repository root and confirmed environment:

```bash
source ~/cd_vlaplan
python scripts/prepare_modality_views.py --dry-run --workers 4
```

The dry-run reads all selected catalogs and measures **every** state and goal;
it writes nothing and does not load the processor. For a bounded development
run, add `--limit-tasks 1` or repeat `--task-id TASK_ID`. Such runs always retain
`complete_selected_coverage=false` and cannot authorize materialization.

The following longer command is left to the operator. It uses only the locally
cached frozen Qwen processor, no model weights, network or GPU inference:

```bash
python scripts/prepare_modality_views.py --qualify --workers 4 \
  --output outputs/modality_views/qualify-001
```

Qualification checks source-goal evaluation against the trusted checker on all
collected states. It reads existing process inputs produced by the BFS, BFWS
and paired-additive family builders, validates their observed-state binding,
and retains their bounded Search Memory and candidate information. BFWS's
candidate symbol table remains common information. Family chat builders supply
the system/user template; no teacher target is attached. Every selected decision
gets all three full-input token counts, without further memory compaction.
Per-decision token/page measurements are retained in compressed task files.

The actual frozen processor measures page grids and token expansion; a complete
multimodal input per worker is cross-checked through the full processor. Every
task's densest observation, its context and its goal pages receive original and
actual processed-pixel previews, covering every domain and goal form. The
report includes page/token distributions, PNG sizes, composition timings,
storage estimates and relative sequence-memory/attention-work estimates.
Actual GPU throughput and peak memory remain separately unqualified.

All stages emit completed/total, elapsed and ETA, with ten-second heartbeats.
Existing output attempts are never silently replaced. Exit 0 means the requested
stage ran (inspect `complete_selected_coverage` for bounded runs), 1 means an
invalid input/gate or execution error, and 2 means `VALID_STOP` for context
capacity. A layout dry-run PASS is not model-input readiness.

## Approval and materialization

Only a **complete PASS qualification** fitting one of 8K/16K/32K can reach this
step. A human must review the full `previews.json` set for clipping, readable
labels after processing, ordered argument associations and quantifier scope.
The human must also approve the recommended larger context, if any. Approval
is recorded separately; the tool never infers it from elapsed time or a preview
being generated. `views-approval.template.json` intentionally cannot authorize
anything until the human fills its fields from a successful report.

After those conditions are met, the operator can run:

```bash
python scripts/prepare_modality_views.py --materialize --workers 4 \
  --qualification outputs/modality_views/qualify-001/report.json \
  --approval path/to/approved-views.json \
  --output outputs/modality_views/materialize-001
python scripts/prepare_modality_views.py --check --workers 4 \
  --qualification outputs/modality_views/qualify-001/report.json \
  --approval path/to/approved-views.json \
  --output outputs/modality_views/materialize-001
```

An interrupted materialization can use the same arguments plus `--resume`.
Completed task manifests are checked and reused; partial task outputs may be
finished, but cannot supply a completion result. A finished attempt uses
`--check`, which performs semantic/readiness checks without rewriting files.
Missing or mismatched approval, partial qualification, changed task bindings,
missing pages, or future-image bindings stop explicitly.

## Handoff to #73/#74

The successor is separate from the preserved #71 two-image freeze and receipts.
Its constants are in `modality_view_preparation.CONTRACT`; the readable copy is
`views-contract.json`. Each compressed task manifest links source goal and types,
normalized execution goal, original catalog and scene paths, unchanged split,
reference costs, source trace paths, reusable pages, per-state drawing recipes,
and ordered decision input-page bindings. Successor/candidate indices are
execution metadata; only the bound source state's pages are inputs.

`ModalityViewStore(root, report_path).observations(task_id, algorithm,
decision_index, family_input)` consumes an authorized completed materialization.
It returns three `PagedModalityObservation` objects with model-facing messages,
ordered role-labelled pages and token counts. All pages are attached anew on
every call; only state raster composition is cached. Context overflow stops
before inference. #73/#74 still own their release and training/evaluation
prerequisites; this implementation does not claim those stages complete.
