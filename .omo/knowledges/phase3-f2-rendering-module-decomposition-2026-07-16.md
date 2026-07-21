# Phase 3 F2 Rendering Module Decomposition

The legacy `src.data_collect.rendering` import path remains a compatibility facade. Its exports now come from focused modules rather than `rendering_implementation.py`:

- `render_types.py`: contracts, protocols, constants, and preflight DTOs.
- `render_archive.py`: bounded, validated PNG archive extraction.
- `render_fake.py`: deterministic local/test backend.
- `render_backends.py`: Planimation hosted renderer and local fallback.
- `render_gates.py`: result persistence, contract validation, and accepted/rejected metadata creation.
- `render_preflight.py`: curriculum profile and renderer readiness checks.

Behavioral constraints retained during extraction:

- Only `RuntimeError` from hosted visualization selects the local renderer fallback.
- Archive validation errors are retried as rendering failures rather than converted to local fallback.
- Unexpected adapter programming errors, including `AttributeError`, still propagate.
- Render outcomes are persisted before acceptance validation.

Verification commands:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_rendering.py tests/data_collect/test_imports.py tests/data_collect/test_cli.py tests/data_collect/test_generate_orchestrator.py tests/test_planimation_phase1.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright src/data_collect/render_types.py src/data_collect/render_archive.py src/data_collect/render_fake.py src/data_collect/render_backends.py src/data_collect/render_gates.py src/data_collect/render_preflight.py src/data_collect/rendering.py
```

Observed results: 38 tests passed and basedpyright reported zero errors, warnings, and notes.
