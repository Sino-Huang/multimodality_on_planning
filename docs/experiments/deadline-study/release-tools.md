# Deadline artifact release tools

These tools prepare #108's artifacts; they do not declare #77's decision, #100's
conclusion or the release complete. Package only terminal runs after their
independent verification. The actual release must carry the completion ledger
and the permitted claims from the chosen study route.

## Prepare from the original workspace

```bash
source ~/cd_vlaplan
python scripts/prepare_deadline_release.py \
  --config configs/experiments/issue75/experiment.json \
  --config configs/experiments/issue76/experiment.json \
  --output outputs/deadline_release/release-001 --dry-run
```

Run the same command without `--dry-run` to produce the artifact directory.
A live or absent experiment is rejected. Existing artifact directories containing
an archive/index are preserved; use a fresh directory after an interrupted export.
No model calls, training, scene regeneration or changes to original attempts occur.

The package contains:

- `index.json`: exact task/episode membership, training record IDs, source configs,
  final-adapter locations, model revision, code commit, package versions and sizes.
- `replay-assets.tar.gz`: original receipts, logs, episode records, source task and
  trace files, source-view manifests/catalogs, and existing images for selected
  tasks. Relative paths are retained; original receipts are not rewritten.
- Uniquely named final-adapter weight links, ready for upload. They reference the
  existing verified final weight files; optimizer state and intermediate training
  checkpoints are not duplicated in the replay archive.

This is a retained-evaluation replay release, not a full training-corpus mirror.
Full retraining still requires the separately retained #72/#73/#74 assets.
The base Qwen weights are not distributed here. Upload the index, replay archive,
final adapters and the final study report together under the eventual release tag.
Do not describe this preparation dry-run as an already published release.

## Replay restored assets

After downloading `index.json` and `replay-assets.tar.gz` from the published
release, use the code commit recorded in the index and the planning Python
environment. The index records the relevant installed package versions, including
Plado, PyTorch, Transformers, PEFT and Pillow. DejaVuSans must be available for
layout measurements. The pinned Qwen processor/tokenizer must be cached; CPU
replay does not need the base model weights or final adapters loaded into memory.

For example, with downloaded assets in `outputs/deadline_release/download-001`:

```bash
source ~/cd_vlaplan
mkdir -p /tmp/deadline-study-restored
tar -xzf outputs/deadline_release/download-001/replay-assets.tar.gz \
  -C /tmp/deadline-study-restored
CUDA_VISIBLE_DEVICES='' python scripts/replay_deadline_release.py \
  --index outputs/deadline_release/download-001/index.json \
  --assets-root /tmp/deadline-study-restored \
  --output /tmp/deadline-study-replay.json
```

The portable replay entrypoint reads the frozen task selection, seeds and original
outcomes, reconstructs every declared episode through the trusted runtime, checks
its modality-specific page/token bindings and recomputes point metrics. It does
not activate a new training run or alter historical authorization receipts. Missing
episode coverage remains `PARTIAL` with exit code 2. A replay PASS does not change
a retained `VALID_STOP` performance verdict into scientific success.

For model use, download each named adapter asset in `index.json` and place it at
its recorded relative `path` below the restored root; `adapter_config.json` is
already included in the replay archive. The final study report must distinguish
available adapters, missing cells, completed execution and performance-gate success.

## Preparation validation

The initial visual-v5 dry-run enumerates 8,172 replay assets (250,162,123 bytes),
864 retained episodes and four separate final adapters (2,793,709,152 bytes).
It writes no package. Tests check explicit selected-task dependencies, separate
weight links, refusal to overwrite original experiments or existing packages,
and refusal to export live runs. A bounded real-data test restores and replays
one exact-reference episode for each algorithm from a different assets root,
correctly reporting the other 860 episodes as missing instead of claiming full
coverage. The final published package still requires a full restored-asset replay.
