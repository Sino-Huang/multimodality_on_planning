---
slug: outputs-vlm-dataset-layout
status: ready-for-execution
intent: clear
review_required: false
pending-action: execute the three-category output migration
approach: Move all fifteen live flat roots into reasoning_traces, image_frames, or deprecated; create physical immutable VLM-record copies; quarantine the failed receipt sidecars; replace GPFS-incompatible renameat2 receipt behavior with ordinary locked rename plus append-only receipts.
---

# Output Layout Decisions

- Top level after migration: exactly `outputs/reasoning_traces/`, `outputs/image_frames/`, and `outputs/deprecated/`.
- Curriculum traces move physically to `reasoning_traces/curriculum/`.
- VLM JSONL records are physical copies in `reasoning_traces/vlm_records/`, not symlinks. Their canonical source remains in the corresponding moved pilot frame run.
- Frame/state-cache runs move physically to `image_frames/`.
- All twelve classified historical runs move to `deprecated/phase3/`; existing deprecated content remains untouched.
- The matching failed `prepared` receipt sidecars are validated and ordinary-renamed into `deprecated/receipts/failed-output-reorganization-20260726/`, then documented by a new append-only recovery receipt.
- New migration receipts are append-only `O_EXCL` journal records. GPFS ordinary rename is allowed only under exclusive lock, same-device checks, pre/post snapshots, and explicit no-overwrite checks.
- No `outputs/datasets` view, compatibility aliases, or immutable-manifest rewriting is permitted.
