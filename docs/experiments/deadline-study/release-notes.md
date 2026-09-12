# Deadline study v1: development feasibility and limitations

This release preserves **complete negative/mixed development evidence**, not a successful final-test or controlled cross-modality result. #77 selected the declared **NO_GO** route to #100 and #108.

- Visual #75 v5: four final adapters, 43,876 training records across algorithms, two epochs, training seed 17, 864 episodes across 42 task groups. The frozen outcome remains VALID_STOP because BFWS success is 66.7% < 80%. BFS and additive SFT success is 100% on their selected panels; additive random-valid also reaches 100%.
- Multimodal #76: four final adapters, 512 records and one epoch / 16 updates per algorithm, seed 17, 48 episodes in storage, blocksworld and ferry. The frozen outcome remains VALID_STOP: SFT succeeds in 0/3 BFS, 0/3 BFWS and 1/3 for each additive setting. All four fail both success and invalid-operation thresholds.
- All **912 retained episodes** were independently replayed from a separately restored artifact package, with matching point metrics and zero model calls.
- The visual and multimodal training schedules are unmatched. No intrinsic modality effect, held-out generalization, training-seed variance, DAgger, end-to-end successor, replication or transfer claim is supported.

## Contents

- `index.json`: source configs, exact training record/task/episode IDs, model/code revisions, package versions and asset locations.
- `replay-assets.tar.gz`: original receipts, logs, episode records, task/trace metadata, selected view catalogs and existing images. This is a retained-evaluation replay bundle, not a full training-corpus mirror.
- Eight named final LoRA adapter `.safetensors` assets. Matching `adapter_config.json` files are included at their original relative locations in the replay bundle. Base Qwen weights are not included.
- `report.md`, `core-results.csv`, `compute-accounting.json`, `completion-ledger.json`, `decision.json`, `restored-replay-verification.json`, and the multimodal completion/parent-progress evidence.

The report distinguishes the #54 v3 defects, corrected v6 corpus and interrupted broad evaluation, v7 resource admission and completed v8 zero-gain VALID_STOP, plus the separate #67 curriculum/heuristic limitations. The original v7 receipt is unavailable; its CPU admission reconstruction is labelled explicitly.

## Replay

Use the repository code commit and planning-package versions recorded in `index.json`, with DejaVuSans and the pinned Qwen processor/tokenizer available. CPU replay needs neither GPU model calls nor base-model weights loaded into memory.

```bash
mkdir -p /tmp/deadline-study-restored
tar -xzf replay-assets.tar.gz -C /tmp/deadline-study-restored
CUDA_VISIBLE_DEVICES='' python scripts/replay_deadline_release.py \
  --index index.json --assets-root /tmp/deadline-study-restored \
  --output /tmp/deadline-study-replay.json
```

For model use, place each downloaded adapter asset at its relative `path` from `index.json`; the matching adapter config is already restored. Full retraining requires the separately retained #72/#73/#74 corpus resources.

#90–#95/#97/#109 and optional #78–#84 were closed **not planned**, not executed. Previously deferred end-to-end/robustness/replication/transfer tickets remain unmeasured. The completion ledger preserves that distinction. The parent research program is not claimed complete.

Known timed #75 attempts plus #76 total 80.42 wall-clock hours, not GPU-hours; earlier historical training and CPU packaging/audits are excluded from that sum. #76 used 64.92 minutes under its four-hour cap. No further GPU work was launched after NO_GO.
