# F2 Persisted Contract Remediation

## Verdict

APPROVE for the persisted pair/state release-contract boundary and fixture capability. This does not approve active-corpus rollout.

## Delivered

- Added `planimation_persisted_contracts.py` as the typed persisted JSON boundary used by pairing-output and release validation.
- Pair `source_line_index`, `frame_count`, `plan_length`, `trace_size_chars`, and `vfg_action_count` use exact integer checks. Python booleans are rejected.
- State `step_index` uses the same exact integer check. Success and failed records have exclusive allowed field sets; established optional renderer metadata remains accepted and typed when present.
- Invalid source-plan cardinality now produces a controlled failed state row instead of a `KeyError` in state ordering or hybrid-manifest receipt creation.

## Regressions

- Copied release fixture with boolean `plan_length` and `trace_size_chars`: release exited `1` with `pair plan_length must be an integer` and `pair trace_size_chars must be an integer`.
- Copied release fixture with boolean state `step_index`: release exited `1` with `state render step_index must be an integer`.
- Mixed success/failure state fields are rejected by release.
- Malformed source-plan cardinality writes one controlled failed state row without an ordering or manifest `KeyError`.

## Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_planimation_pairing.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/planimation_persisted_contracts.py scripts/phase3/planimation_pairing_implementation.py scripts/phase3/verify_planimation_vlm.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/planimation_persisted_contracts.py scripts/phase3/planimation_pairing_implementation.py scripts/phase3/verify_planimation_vlm.py
```

Observed: `50 passed in 6.43s`; basedpyright reported `0 errors, 0 warnings, 0 notes`; compileall exited `0`; LSP diagnostics were clean for all changed production and test files.

## Manual CLI Surface

A fresh test fixture was generated through the existing fixture builder and exercised with:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/phase3_release_final_manual_qa_phase3_final_manual_qa --mode release
```

The unmodified fixture exited `0` and reconciled one pair, four state renders, one train full record, one train step record, and two train search-traversal records. The intentionally corrupted fixture probes above exited `1` with the stated controlled errors.
