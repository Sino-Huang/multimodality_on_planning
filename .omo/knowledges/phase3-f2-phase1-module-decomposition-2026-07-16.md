# Phase 3 F2 Phase 1 Module Decomposition

`scripts.planimation_phase1` is now an explicit compatibility facade over focused modules:

- `planimation_phase1_manifest.py`: manifest parsing, local PDDL validation, asset download, and JSON output.
- `planimation_phase1_client.py`: endpoint candidates, preflight, PDDL upload, and VFG visualization requests.
- `planimation_phase1_frames.py`: local VFG PNG rendering and delegation to the shared safe archive extractor.
- `planimation_phase1_runner.py`: manifest render orchestration and output reporting.
- `planimation_phase1_cli.py`: CLI parser and operational process boundary.

Compatibility guarantees retained:

- The facade aliases `post_pddl_for_vfg`, `post_vfg_for_visualisation`, `preflight_host`, and `render_vfg_to_local_png_frames` directly.
- Phase 3 and data-collection renderer imports keep their existing callable signatures.
- Local fallback remains PNG-only. Archive extraction delegates to `src.data_collect.render_archive`.
- Expected request failures are collected by remote request loops; unexpected adapter errors propagate.

Verification:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/test_planimation_phase1.py tests/data_collect/test_rendering.py tests/data_collect/test_imports.py tests/data_collect/test_cli.py tests/data_collect/test_generate_orchestrator.py tests/phase3/test_planimation_pairing.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/planimation_phase1.py scripts/planimation_phase1_manifest.py scripts/planimation_phase1_client.py scripts/planimation_phase1_frames.py scripts/planimation_phase1_runner.py scripts/planimation_phase1_cli.py tests/test_planimation_phase1.py
```

Results: 83 tests passed; basedpyright reported zero errors, warnings, and notes. All Phase 1 modules are at or below 149 pure LOC.
