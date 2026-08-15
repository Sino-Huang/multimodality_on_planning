# Phase 3 F2 Compatibility Facade Remediation

## Changes

- Kept `src.data_collect.rendering`, `scripts.planimation_phase1`, and `scripts.phase3.planimation_pairing` as stable import facades.
- Relocated their implementations behind corresponding implementation modules and retained legacy public and verifier-facing private symbols.
- Added direct facade import coverage in `tests/data_collect/test_imports.py`.

## Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_imports.py tests/data_collect/test_rendering.py tests/data_collect/test_generate_orchestrator.py tests/data_collect/test_cli.py tests/test_planimation_phase1.py tests/phase3/test_planimation_pairing.py tests/phase3/test_planimation_search_traversal.py tests/phase3/test_verify_planimation_vlm.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright src/data_collect/rendering.py src/data_collect/rendering_implementation.py scripts/planimation_phase1.py scripts/planimation_phase1_implementation.py scripts/phase3/planimation_pairing.py scripts/phase3/planimation_pairing_implementation.py tests/data_collect/test_imports.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q src/data_collect/rendering.py src/data_collect/rendering_implementation.py scripts/planimation_phase1.py scripts/planimation_phase1_implementation.py scripts/phase3/planimation_pairing.py scripts/phase3/planimation_pairing_implementation.py tests/data_collect/test_imports.py
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/f1_search_traversal_release_surface --mode release
```

Observed results: 90 tests passed, basedpyright found zero errors/warnings/notes, compileall exited zero, and the fixture release verifier reconciled one pair, four renders, one full record, one step record, and two traversal records.
