# CGAS Persisted Alignment Acceptance Binding

- `scripts.phase3.cgas_alignment.verify_persisted_alignment()` is the trust boundary for Todo 3 persisted alignment output consumed by Todo 4.
- It validates the exact manifest shape, schema version, source digest, alignment digest, source-derived split counts, and structural `render_manifest_digest`; it then verifies each alignment row has one known source transition and no source transition is absent or duplicated.
- Row checks bind `split`, `state_before_hash`, `action`, `vision_status`, and `vfg_action_index` to the authoritative source row. The PNG path must decode and its bytes must match `png_sha256`.
- `cgas_certificates._evaluate()` calls this gate before it constructs records, so both `build_steps()` and `verify_steps()` reject invalid Todo 3 persistence without changing their existing schema, certificate, counterfactual, or transaction paths.
- The focused regression is `tests/phase3/test_cgas_certificates_alignment_binding.py`; its fresh corpus remains 12 rows and it covers manifest absence/malformed/digest tampering, path/hash/status/action/state/split mutation, and duplicate/missing/unknown transition sets.
