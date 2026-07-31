# CGAS Characterization Determinism Oracles

- Use only the explicit synthetic 481-row fixture for finalization determinism tests; do not run product data or network workflows.
- Same run-contract bytes and fingerprint imply byte identity for the final bundle, parsed header fingerprint/member SHA-size table, JSONL, and manifest across forward, reverse, and resumed checkpoint histories.
- A `shard_count` difference deliberately changes the run contract, fingerprint, embedded contract member, and bundle SHA-256. Its bundle SHA-256 is contract-scoped provenance identity, not evidence against cross-shard scientific determinism.
- Across different shard-count contracts, compare exact JSONL and manifest bytes plus manifest `artifact_sha256`, `source_records_sha256`, object/split counts, and implementation digests.
- Focused validation: run assembly, bundle, final-publication, verifier, CLI, and determinism tests twice; then run Basedpyright, compileall, LSP diagnostics, and `git diff --check`.
