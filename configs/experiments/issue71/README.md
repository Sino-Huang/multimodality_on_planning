# Issue 71 retained v1 candidate

The active successor is [v2](v2/README.md). The default preflight now inspects v2.
This document and the adjacent v1 manifests retain the initial stopped candidate;
their production blockers are historical, not a statement that profiles do not exist.

Status: **not authorized; #71 remains open.** These five component manifests
record the proposed production settings and an explicit `VALID_STOP`, not a
completed modality freeze or permission to launch an experiment.

Run the short, read-only preflight:

```bash
source ~/cd_vlaplan
python scripts/prepare_modality_issue71.py --dry-run --freeze configs/experiments/issue71/freeze.json
```

It logs each stage, elapsed time, source counts, and the stop reason. Exit zero
means the dry-run worked. `start_permitted: false` means **do not launch
production**. No HTTP, processor/model loading, rendering, training, or output
writes occur. There is currently no long-run command to hand off for #71.

## Recorded scope

The Cartesian product in `matrix.json` enumerates 12 cells: BFS, full unpruned
BFWS, weighted additive best-first (`g + 3*h_add`), and greedy additive
best-first (`h_add`), each in text-state, visual-state, and multimodal-state.
The optimal A-star attempts remain stopped. This is not a
heuristic-representation comparison.

Every cell has one proposed seed-17 process-SFT run and an independent adapter.
Five evaluation seeds use that one final checkpoint; early/middle checkpoints
are diagnostic only. New matched text adapters are included because the
modality observation format differs from historical text training. Those old
adapters must not silently substitute for a matched text control.

The three existing source corpora contain 125,659 process records before
production modality selection. They are not a released matched training corpus.
The proposed complete-task decision ceiling is 1,024; additive settings stay
paired. Preserve source whole-instance splits and record exclusions. No
full-trace segmentation is proposed. All semantic task/decision associations,
teacher applicability, parity, and token limits remain scientific checks;
there are no hashes, artifact-integrity checks, or regeneration comparisons.

The #54 lesson about shared model input is retained as shared builders and
semantic parity, not its superseded byte-comparison requirement. Hardware
probes compare interpreted operations/runtime behavior, not output bytes.

## Unresolved prerequisites

The representation is already established by #38 and #69/#70: domain-specific
Planimation scenes plus complete labelled relation panels, with a separate
partial-goal image. Relation-panel-only images are not the agreed replacement.
The visual arm still shares textual instructions and Search Memory; it is not
an unannotated-scene perception experiment.

1. Reuse the existing 15-domain map in
   `src/data_collect/configs/curriculum_15_domains.yaml`. All 15 referenced
   profiles under `data/pddl_instances/` exist locally (inspected 2026-09-07).
   Freeze the selected profile paths and qualify their compatibility with the
   actual selected tasks through localhost supplied-plan state/frame and
   partial-goal checks. The #70 room profile is not interchangeable with them.
2. Enumerate the complete matched production selection with source split,
   exact-reference costs and exclusions. Final counts must be recorded before
   rendering. The current manifests record source counts only.
3. Cover BFS and BFWS with the same semantic modality-input boundary and
   position-by-position teacher/live parity tests. #69/#70 implemented the
   additive best-first adapter, not all four family adapters.

These are not resource failures from a running experiment or an undecided
representation. They are unfinished production bindings/implementation coverage.
Do not flip the authorization outcome to PASS. Retain this candidate and stop
record; finish the missing work in a successor with new phase, attempt, receipt,
and output identities. The proposed training/budget/statistical choices also
remain subject to that final freeze; no run has consumed them.

## Mandatory downstream boundary

Every new #72–#77 entry point must load `load_modality_phase`, then call
`ModalityPhase.permission` before source materialization, HTTP, tokenization,
training or model calls. It must stop unless `start_permitted` is true and
retain the returned receipt alongside the phase authorization ID. Both the
phase authorization and matching per-attempt gate/authorization are required.
Historical #70 evidence/replay remains under its own tiny infrastructure
contract; it is not a production entry point and is not retroactively changed.

The gate requires whole-stage, phase-scoped completed predecessor reports.
Render precedes corpus; corpus precedes training; corpus/training precede
hardware qualification; all three precede evaluation. Synthesis requires
complete evaluation. A PASS shard, teacher-forced accuracy, dry-run or a closed
GitHub issue does not substitute for stage completion.

Actual hardware qualification remains downstream work: cover occupied input
bins, test scalar/batch and repeated-batch semantic behavior plus adapter
isolation, measure float32 throughput, try full coverage then the preregistered
cost-only fallback. Do not select by model success. Use one matrix clock and
stop new calls at its cutoff; partial coverage cannot pass. The future long-run
runner must report progress/ETA and a heartbeat within 30 seconds, and concurrent
torch jobs must record distinct explicit rendezvous ports.

Competence and advantage remain separate: invariant-valid success can establish
valid execution on the selected panel without beating the oracle-assisted
random-valid control. It cannot alone establish a learned search advantage.
