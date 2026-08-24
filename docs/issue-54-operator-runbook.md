# Issue #54 operator runbook

Issue #54 uses only phase `issue-111-bfs-expansion-qualified-pilot-v3` and the
process view in `data/bfs_pilot_v3/ms-swift-process`. Operational-SFT is not an
authorized comparator. Run every command from the repository root after
`source ~/cd_vlaplan`.

`scripts/run_bfs_issue54.py` supplies every argument and output path. Run its
five stages in order. Adding `--dry-run` performs that stage's
committed-input preflight without starting an experiment or creating the
requested output root. A later stage intentionally refuses to run until its
predecessor products exist.

## 1. Exact and random-valid references

This creates 45 exact episodes and 225 five-seed random-valid episodes:

```bash
python scripts/run_bfs_issue54.py references --dry-run
python scripts/run_bfs_issue54.py references
```

Monitor `outputs/bfs_phase/issue54-v3-references-progress.json` for the latest
elapsed-time and ETA record, or follow the append-only `.jsonl` file beside it.
The PASS prerequisite for training is
`outputs/bfs_phase/issue54-v3-references/manifests/bfs-references.json`.

## 2. Base-model evaluation

Base inference uses about 18 GB per process on these A100 80 GB GPUs. The
default launcher permits three inference processes per GPU, so all five seeds
can run concurrently while retaining memory headroom:

```bash
python scripts/run_bfs_issue54.py base --dry-run
python scripts/run_bfs_issue54.py base
```

If the base stage was interrupted after creating partial seed roots, validate
and resume those exact attempts instead of deleting them:

```bash
python scripts/run_bfs_issue54.py base --resume --dry-run
python scripts/run_bfs_issue54.py base --resume
```

Each output contains `progress.json`, append-only `progress.jsonl`, replayed
episode evidence, `manifest.json`, and a sibling `.console.log`. The progress
record includes elapsed seconds and estimated remaining seconds over the frozen
45-task dev set.

## 3. Process-SFT training

SFT has a larger footprint than the observed 18 GB inference process. The
default uses two single-GPU SFT processes per GPU: four seeds run concurrently,
then the fifth runs in the first available GPU slot. Each run preserves the
frozen global batch size of 32 with gradient accumulation 32:

```bash
python scripts/run_bfs_issue54.py train --dry-run
python scripts/run_bfs_issue54.py train
```

The two-process training setting is configurable because SFT memory is larger
than inference memory. Before any training output root exists, use
`--training-processes-per-gpu 1` if two concurrent SFT processes do not fit the
available memory.

Concurrent SFT jobs receive distinct torchrun rendezvous ports. If training is
interrupted before a checkpoint is saved, rerun the same `train --dry-run` and
`train` commands. The runner retains the incomplete immutable attempt and
creates the next `-attempt-NNN` output root automatically. Do not pass
`--resume` to the training stage unless checkpoint resume is implemented in a
later revision.

The launcher records the exact command, environment, receipts, and installed
framework versions in `launch.json`. It tees live ms-swift stdout/stderr to
both the terminal and `training.log`, writes the latest step/elapsed/ETA status
to `progress.json`, retains the history in `progress.jsonl`, and records
discovered checkpoint paths in `training-report.json`. With the current
13,434-record training projection, the frozen three-epoch/two-GPU command plans
1,260 optimizer steps.

## 4. Checkpoint evaluation

Every checkpoint from every seed is evaluated with up to three inference
processes per GPU:

```bash
python scripts/run_bfs_issue54.py evaluate --dry-run
python scripts/run_bfs_issue54.py evaluate
```

The adjudicator selects the earliest checkpoint among ties on the frozen
`dev_invariant_valid_episode_success` metric. It does not use the sanity-gate
thresholds as checkpoint-selection tie breakers.

## 5. Sanity adjudication

The runner discovers all five base manifests and every checkpoint-evaluation
manifest, then supplies them to the invariant-aware adjudicator:

```bash
python scripts/run_bfs_issue54.py adjudicate --dry-run
python scripts/run_bfs_issue54.py adjudicate
```

The retained report verifies every episode, checks the complete task-by-seed
products, reports each seed, performs the frozen whole-instance paired
bootstrap, and emits an explicit `PASS`, `VALID_STOP`, `ANCESTOR_STOP`, or
`INVALID` gate receipt. `VALID_STOP` and `ANCESTOR_STOP` include a downstream
`gated-not-run` receipt; `INVALID` is never scientific completion.
