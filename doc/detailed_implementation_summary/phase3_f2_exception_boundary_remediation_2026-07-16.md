# Phase 3 F2 Exception-Boundary Remediation

## Change

The Planimation rendering, pairing, and Phase 1 command paths no longer suppress broad `Exception` handlers with `# noqa: BLE001`.

Expected renderer, filesystem, parsing, archive, image, and validation failures remain controlled outcomes. Unexpected adapter programming errors now propagate to the caller.

The injected Planimation adapters use explicit protocols rather than `Any`-typed callable parameters.

## Regression Coverage

`tests/data_collect/test_rendering.py` injects an adapter that raises `AttributeError` and asserts that `render_candidate()` propagates it rather than storing a failed render result.

## Verification Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_rendering.py tests/test_planimation_phase1.py tests/phase3/test_planimation_pairing.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright src/data_collect/rendering.py scripts/phase3/planimation_pairing.py scripts/planimation_phase1.py tests/data_collect/test_rendering.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q src/data_collect/rendering.py scripts/phase3/planimation_pairing.py scripts/planimation_phase1.py tests/data_collect/test_rendering.py
rg -n 'except Exception|noqa: BLE001' src/data_collect/rendering.py scripts/phase3/planimation_pairing.py scripts/planimation_phase1.py
```

## Results

- Focused regression suite: `57 passed in 2.51s`.
- basedpyright: `0 errors, 0 warnings, 0 notes`.
- Compilation: exit code `0`.
- Broad-exception/noqa scan: no matches in the remediated files.
