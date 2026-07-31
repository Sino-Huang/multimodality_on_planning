# CGAS Qwen-VL Conversion

- The conversion boundary must call Todo4 `verify_steps()` first and consumes only its accepted serialized steps.
- The Qwen manifest binds live source, alignment, steps, and `steps_manifest.json` byte digests, plus split record IDs/digests and every copied image path/byte digest.
- A verifier must check raw canonical JSONL bytes and the complete output tree independently of a recomputable manifest; declared image lists cannot establish absence of orphan or symlinked content.
- Split annotation digests must cover the exact persisted JSONL bytes, including each terminal newline; post-copy image verification is required because source validation alone cannot prove destination integrity.
- 2026-07-28 Todo 5 status: fixture acceptance artifacts were not production data. Fixture-generated Qwen output stayed under Todo 5 evidence until live source, alignment, and steps existed under `data/planning_cgas_v1`.
- 2026-07-31 Todo 6 supersession: the fail-closed release gate published `data/planning_cgas_v1/release_manifest.json` for 12 emitted rows. That manifest is the only authorized handoff for downstream CGAS work; it does not deliver live memory, route labels or calibration, CGAS training or implementation, or attention analysis.
