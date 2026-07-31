# CGAS Dataset Readiness

Date: 2026-07-28

## Decision

Treat `data/phase3_supervised_planning` as a valuable raw BFS trace source, not as a CGAS-ready VLM training dataset.

## Evidence

- `summary.json` contains 411 full BFS traces only; IW, FF, and Graphplan report `skipped_planner_unavailable`.
- Vision diagnostics classify all 3,600 inspected records as `vision_available_unaligned`; images exist but are not verified against a particular supervised transition.
- Phase 3 rows expose BFS queue events and replay transitions, which can derive typed BFS certificates.
- The Phase 3 registry is a no-op discoverability surface. Native Qwen-VL SFT instead requires `conversations` and `<image>` placeholders resolved from `image` paths.

## Implementation Consequence

Before a training dataloader, create a versioned step-level `planning_cgas_v1` corpus with typed certificate targets, one-invariant counterfactuals, provenance, and split-safe aligned observations. Validate converted records through `starVLA/dataloader/vlm_datasets.py` rather than through the registry test alone.

## Research Consequence

The P0 CGAS paper claim requires validated BFS and IW corpus coverage. Keep visual analysis secondary and exclude unaligned images from VLA training. Do not simulate missing IW data or expose oracle queue/novelty state in model inputs or memory.

## Todo 1 Snapshot Contract

- The read-only command is `source ~/cd_vlaplan && python -m scripts.phase3.cgas_readiness_snapshot`.
- Its default artifact is `outputs/cgas_readiness/input_contract.json`; it reports `observed_not_ready` and `readiness_approved: false` even when snapshot creation succeeds.
- It parses the persisted summary and vision diagnostics strictly. Missing or mistyped required summary fields fail nonzero with the precise field name.
- Current observed facts are 411 historical BFS examples, zero IW examples, zero proven step-aligned vision rows, and the active pipeline identifiers `gbfs, ff, iw, graphplan`.
