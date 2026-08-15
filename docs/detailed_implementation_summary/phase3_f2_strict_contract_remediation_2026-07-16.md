# Phase 3 F2 Strict Contract Remediation

## Delivered

- Traversal projection rejects boolean-as-integer values and malformed FF, GBFS, IW, and Graphplan scalar or nested successor fields.
- Hybrid full and step schemas now declare concrete types for root fields, targets, provenance, artifact paths, render receipts, and integer arrays.
- `validate_vlm_record` uses the same generated strict schema contract used for persisted schemas.
- Release validation recursively evaluates each persisted full or step schema for type, const, required-key, closed-object, and typed-array semantics.

## Preserved Boundaries

- Active planners remain exactly `ff`, `gbfs`, `iw`, and `graphplan`; `bfs` is still rejected without aliasing.
- Graphplan remains planner-semantic only and does not acquire a concrete-state or visual boundary.
- Frozen source identity and source-root behavior are unchanged.
- Existing valid and zero-action fixtures remain accepted.

## Verification Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/trace_contracts.py scripts/phase3/planimation_pairing.py scripts/phase3/verify_planimation_vlm.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/trace_contracts.py scripts/phase3/planimation_pairing.py scripts/phase3/verify_planimation_vlm.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.trace_contracts --fixtures tests/phase3/fixtures/traversal_trace_contract_cases.json --report tmp/f2_trace_contract_projection.json
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/phase3_task8_release_fixture --mode release
```

Observed results: 61 focused tests passed, basedpyright reported zero findings, compilation exited zero, the trace CLI projected four valid fixtures and excluded four malformed fixtures, and the persisted release fixture passed release verification.
