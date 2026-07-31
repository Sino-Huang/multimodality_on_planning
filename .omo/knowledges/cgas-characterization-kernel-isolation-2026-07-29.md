# CGAS Characterization Kernel Isolation

- `cgas_partition_characterization.py` is the orchestration facade. Its `_characterize()` normalized AST is frozen at SHA-256 `d2867a5e5960b4b4b3434253f59aeee9f274f45435036d5f9bbe239bd3c17a47`.
- `cgas_characterization_rows.py` owns the characterization limits, row projection, planner-record projection, composition descriptors, and canonical manifest writing.
- The facade re-exports `canonical_composition_signature` and `_planner_record` as the exact row-module function objects for compatibility.
- The representative local Blocksworld canonical row is 3,850 bytes with SHA-256 `06aaa5949c38b91a1f461f88629de7bcfad96fd6957862beef09b19ddcdd4458`.
- Manifest provenance continues to digest the facade module through its compatibility writer, preserving the existing manifest schema and source-byte semantics.
