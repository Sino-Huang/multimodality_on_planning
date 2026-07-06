- Chose a minimal CLI contract now: help output shows `generate` and `inspect-tools`, while execution remains intentionally unimplemented until later phases.
- Kept the package surface stable by creating all placeholder modules early so downstream tasks can fill behavior without renaming imports.
- Verified with: `source ~/cd_vlaplan && source .venv/bin/activate && python -m pytest tests/data_collect -q`.
- Locked accepted instance IDs to `{domain_id}-{split}-{bucket}-{index:04d}` and candidate IDs to `{domain_id}-{split}-{bucket}-attempt-{attempt_index:06d}` via constructor validation, so later orchestrator code cannot silently drift from the contract.
- Normalized PDDL hashing strips `;` comments and tokenizes away whitespace-only differences before hashing, while keeping the raw SHA-256 alongside the normalized hash for provenance.
- Resume protection preserves an existing `status="accepted"` result file unless `force=True`; non-accepted metadata remains replaceable so later retry loops can update rejection evidence.
- Added summary aggregation helpers that count accepted instances by split/bucket/domain and rejected candidates by reason, matching the `summary.json`/`result.json` style used in `scripts/planimation_phase1.py`.
- Verified Task 3 with: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_metadata.py -q`.
- Kept the config schema intentionally small for Task 2: one curriculum file plus one dependency file, with `generator_domain_id` carrying the adapter mapping (`15puzzle->npuzzle`, `depot->depots`, `towers_of_hanoi->hanoi`) and resolved paths derived in Python instead of duplicated in YAML.
- Stored the `.yaml` files as JSON-formatted YAML so the loader works in the current environment without adding a new `PyYAML` runtime dependency; `src.data_collect.config` still falls back to real YAML parsing when PyYAML is available later.
- Verified Task 2 with: `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_config.py -q` and `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect -q`.
- Chose to keep `inspect-tools` read-only and JSON-first: it reports capability state and exits nonzero only for hard readiness blockers (missing generator root or missing required render profiles), without mutating `.venv` or installing dependencies.

## Task 13 consultation - recommended decision (2026-06-12T03:02:00+10:00)

- Do not merge 13/15 or 12/15 shards.
- Do not keep extending long generation commands as the primary strategy.
- Prefer two targeted adapter repairs: a structural-parameter sweep for `storage`, and a real Planimation-compatible `sokoban` domain/problem/AP alignment or converter.
- Generate only replacement `storage` and `sokoban` shards into `/tmp`, verify each reports 240 accepted with train/dev/test quotas and zero render/hash failures, then replace only the incomplete shard roots.
