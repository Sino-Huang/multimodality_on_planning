# Phase 3 F2 Rendering Module Decomposition

## Change

Replaced the 747-line `src/data_collect/rendering_implementation.py` monolith with focused rendering modules while preserving `src.data_collect.rendering` as the stable public API.

`render_types.py` owns contracts and constants, `render_archive.py` owns safe archive extraction, `render_fake.py` owns deterministic artifacts, `render_backends.py` owns Planimation invocation and fallback, `render_gates.py` owns persistence and metadata decisions, and `render_preflight.py` owns readiness checks.

## Preserved Behavior

- The facade still exports the legacy rendering API and `_extract_png_archive`.
- Hosted visualization falls back locally only for `RuntimeError`.
- Archive parsing errors are handled by the render retry boundary and do not trigger fallback.
- Unexpected adapter contract errors propagate.
- Result metadata is persisted for both accepted and rejected render outcomes.
- All extracted rendering modules are within the 250 pure-LOC limit.

## Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_rendering.py tests/data_collect/test_imports.py tests/data_collect/test_cli.py tests/data_collect/test_generate_orchestrator.py tests/test_planimation_phase1.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright src/data_collect/render_types.py src/data_collect/render_archive.py src/data_collect/render_fake.py src/data_collect/render_backends.py src/data_collect/render_gates.py src/data_collect/render_preflight.py src/data_collect/rendering.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q src/data_collect
git diff --check
```

Observed result: the targeted dependent suite passed with `38 passed in 1.21s`; basedpyright reported zero errors, warnings, and notes; compilation and diff validation passed. A direct `FakeRenderer` import-and-render smoke test created a trace and PNG frame successfully.
