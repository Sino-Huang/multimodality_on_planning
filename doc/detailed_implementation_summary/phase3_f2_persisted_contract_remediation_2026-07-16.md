# Phase 3 F2 Persisted Contract Remediation

## Objective

Close the persisted pair/state boolean-as-integer release bypass without changing frozen source roots, active planners, or the compatibility facade.

## Implementation

- Extracted persisted pair and state-record parsing to `scripts/phase3/planimation_persisted_contracts.py` using recursive JSON-safe types.
- Replaced coercive persisted checks with exact integer checks for pair manifest size fields and state-render `step_index`.
- Routed release and pairing-output validation through the shared parser.
- Enforced exclusive success/failure state fields while allowing existing optional renderer metadata only in the appropriate variant and validating its type when present.
- Fixed ordering and hybrid-manifest state-ID derivation for controlled failed cardinality rows that have no transition.
- Added release-level copied-fixture regressions for both boolean bypasses and mixed state variants, plus a renderer regression for malformed source-plan cardinality.

## Verification Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_planimation_pairing.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/planimation_persisted_contracts.py scripts/phase3/planimation_pairing_implementation.py scripts/phase3/verify_planimation_vlm.py tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/planimation_persisted_contracts.py scripts/phase3/planimation_pairing_implementation.py scripts/phase3/verify_planimation_vlm.py
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/phase3_release_final_manual_qa_phase3_final_manual_qa --mode release
```

## Observed Results

- The focused suite passed: `50 passed in 6.43s`.
- Basedpyright reported `0 errors, 0 warnings, 0 notes`; compileall exited `0`; LSP diagnostics were clean for every changed file.
- The fresh release fixture exited `0` with one pair, four state renders, one train full record, one train step record, and two train search-traversal records.
- Pair `plan_length`/`trace_size_chars` boolean probes and state `step_index` boolean probe each exited `1` with controlled exact-integer errors.
