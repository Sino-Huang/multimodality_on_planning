# Phase 3 F2 Pairing And Release Modularization

- The stable `planimation_pairing.py` facade delegates to `planimation_pairing_implementation.py`, which synchronizes the monkeypatchable `_source_jsonl_rows` and `_source_root_snapshot` hooks into the source and manifest modules before public pairing operations.
- Pairing responsibilities are separated into source provenance, reasoning, schemas, rendering, manifest construction, replay, VLM records, and validation. Release verification is split between orchestration and typed file/schema/artifact validation.
- Active JSON payload boundaries use `JSONValue`, not `Any`. The split module headers contain only actual runtime dependencies.
- Verification command: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py -q` returned `53 passed in 8.20s`.
- The release CLI was run with a generated production-complete fixture in `release` mode and reported one pairing record, four state-render records, one full record, one step record, and two search-traversal records for train.
