# CGAS Phase 3 Pilot Expansion Materialization (2026-08-09)

The approved 90-instance pilot now has a deterministic certificate-source index under `tmp/cgas-phase3-pilot-expansion-index-v1`.

- Index rows: 31,171.
- Replay-plan rows: 790.
- Off-plan-only rows: 30,381.
- Unique expansion states: 16,822.
- Existing render coverage: 0; all 16,822 states remain requested.
- Index SHA-256: `46d1e7c1c0a6a133372782e691888840a74f3d3732dd625b5e2d8611fdf5d390`.
- Missing-render request SHA-256: `13db7cba5fb1cf885bd203ff657e5c7714bda6f832c5970dbfe5a9dee36d0585`.

The materializer re-verifies Gate 0b, signed v3 stream bindings, planner-specific replay membership, final-width IW events, exact frozen budgets, and immutable publication. The render audit validates canonical state hashes and existing PNG byte digests without invoking a renderer.

No approved policy chooses one action target for an off-plan expansion. All successors/actions remain in the source index, and no Qwen rows were created. The pending options are recorded in `.claude/evidence/cgas-phase3-pilot-materialization/OWNER-DECISION-action-target.md`.

**Why:** The certificate-source milestone is complete, but action-supervised projection and rendering remain blocked by an explicit owner policy and zero current pilot-state coverage.

**How to apply:** Use the committed materialization report and coverage report as the canonical bindings; consume the temporary index only after verifying its recorded SHA-256. Do not force off-plan rows into `planning_cgas_v1`.
