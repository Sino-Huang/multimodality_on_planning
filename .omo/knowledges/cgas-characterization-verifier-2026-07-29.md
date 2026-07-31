# CGAS Characterization Verifier

Date: 2026-07-29

- `scripts.phase3.cgas_characterization_verifier` is a read-only closure root whenever it is present. Explicit module-root callers also include it, so its bytes invalidate a persisted run contract.
- Checkpoint roots contain exactly `run-contract.json` and `checkpoints/`; final roots contain exactly `run-contract.json`, `characterization.jsonl`, and `characterization_manifest.json`.
- The verifier opens roots and leaves with descriptor-relative `O_NOFOLLOW` reads, rejects symlinks and special entries, parses canonical JSON only once at each boundary, recomputes the current run contract, and validates checkpoint identity bindings.
- A valid checkpoint root may be incomplete and reports `valid=true`, `complete=false`, `publishable=false`. A final root is publishable only after exact 481-row coverage, current source/PDDL identities, current implementation hashes, literal `owner_approved=false`, and manifest/count/digest/policy checks.
- Final BFS/IW records are replayed with the repository PDDL parser, grounding, and `replay_plan`; their persisted replay output must match exactly. Planner records allow no oracle/recovery fields and must agree on limits, implementation, exact-search metadata, retained-trace completeness, and source eligibility.
- Checkpoint `row_digest` is recomputed as SHA-256 over the canonical current kernel row bytes. Final roots deliberately contain no checkpoints: every final JSONL row is recomputed through unchanged `_characterize()` and compared byte-for-byte, making persisted trace/accounting claims non-authoritative.
- The secondary planner gate matches `exact_search.status` exhaustively. `exact_solution_replayed` records must replay and match goal/trace/eligibility policy; authoritative `not_exact_solution` records are valid only with no plan and no replay-success claim. Canonical failed rows retain `bfs=None` and `iw_width_1=None`.
- Verification roots and checkpoint directories must be owned by the current effective user and mode `0700`; inspected contract, final, and checkpoint leaves must be owned mode `0600` with one link. Typed `CheckpointError` failures are converted to deterministic invalid terminal reports.

## Verification

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 pytest -q tests/phase3/test_cgas_characterization_verifier.py tests/phase3/test_cgas_characterization_contract.py tests/phase3/test_cgas_characterization_checkpoint.py tests/phase3/test_cgas_characterization_checkpoint_publication.py tests/phase3/test_cgas_characterization_types.py tests/phase3/test_cgas_serialization.py tests/phase3/test_cgas_partition_characterization.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_verifier.py scripts/phase3/cgas_characterization_contract.py tests/phase3/test_cgas_characterization_verifier.py
```
