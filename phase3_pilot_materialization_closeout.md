# Phase 3 Pilot Materialization Closeout

Implemented and verified on 2026-08-09.

- Index: `tmp/cgas-phase3-pilot-expansion-index-v1/pilot-expansion-index.jsonl`
- Index SHA-256: `46d1e7c1c0a6a133372782e691888840a74f3d3732dd625b5e2d8611fdf5d390`
- Rows: 31,171 total; 790 replay-plan; 30,381 off-plan-only.
- States: 16,822 required; 0 covered; 16,822 missing.
- Coverage SHA-256: `33b9ddcb43b4878affded44a742610e58bcc568289554b7c8dbab572ec63d58e`.
- Missing request SHA-256: `13db7cba5fb1cf885bd203ff657e5c7714bda6f832c5970dbfe5a9dee36d0585`.
- Gate 0b: 281 candidates, 562 signed v3 streams, 3,000,099,088 bytes.
- Pending: owner decision for off-plan action targets; no Qwen rows were created.
- Focused: 8 passed; regression: 42 passed; broad CGAS: 484 passed, 3 pre-existing probe-binding failures.
- Ruff and basedpyright passed over changed Python files.
- Immutable characterization and approval digests are unchanged.
