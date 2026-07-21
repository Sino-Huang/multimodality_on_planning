# Phase 3 F2 Phase 1 Module Decomposition

## Change

Removed the 665-line Phase 1 implementation monolith. `scripts.planimation_phase1` now provides the legacy public surface by direct aliases to manifest/assets, remote-client, local-frame, runner, and CLI modules.

## Behavior Preserved

- Legacy rendering and Phase 3 callables retain their module-path facade and signatures.
- Endpoint candidate order and explicit endpoint overrides remain unchanged.
- Host preflight turns named request failures into a typed serializable report.
- The local fallback writes decodable PNG frames and uses the shared bounded safe archive extractor.
- Unexpected request-adapter programming errors propagate instead of being converted to a false render success.

## Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/test_planimation_phase1.py tests/data_collect/test_rendering.py tests/data_collect/test_imports.py tests/data_collect/test_cli.py tests/data_collect/test_generate_orchestrator.py tests/phase3/test_planimation_pairing.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/planimation_phase1.py scripts/planimation_phase1_manifest.py scripts/planimation_phase1_client.py scripts/planimation_phase1_frames.py scripts/planimation_phase1_runner.py scripts/planimation_phase1_cli.py tests/test_planimation_phase1.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/planimation_phase1.py scripts/planimation_phase1_manifest.py scripts/planimation_phase1_client.py scripts/planimation_phase1_frames.py scripts/planimation_phase1_runner.py scripts/planimation_phase1_cli.py tests/test_planimation_phase1.py
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py --help
git diff --check
```

Results: 83 tests passed in 3.04 seconds; basedpyright returned zero errors, warnings, and notes; compilation and diff validation passed. The CLI displayed its command help and rejected an incomplete `render` invocation with the required `--manifest` and `--output-dir` diagnostic.
