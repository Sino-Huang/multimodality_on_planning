# Phase 3 Planimation Render Cache Hardening

Todo 3 makes replay-state rendering content-addressed and verifies every cached artifact before reuse. Profile selection now comes from the repository-managed curriculum configuration; historical render-result profile paths are not accepted as runtime inputs.

Each cache result persists repository-relative `profile_path`, profile/domain/problem/state hashes, renderer configuration identity, derived-PDDL hash, VFG hash, PNG SHA-256, decoded dimensions, and the deterministic `nontransparent_pixels` semantic image check. A cache hit validates all of those values, reparses derived PDDL state, validates VFG structure, and decodes the PNG.

Raster ZIP extraction now validates all entries before writing. Only bounded PNG files contained within the requested output root are accepted; traversal paths, symlinks, oversized members, excessive compression, and excessive aggregate payloads are rejected.

## Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py tests/data_collect/test_rendering.py tests/test_planimation_phase1.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/planimation_pairing.py src/data_collect/rendering.py scripts/planimation_phase1.py tests/phase3/test_planimation_pairing.py tests/data_collect/test_rendering.py tests/test_planimation_phase1.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/planimation_pairing.py src/data_collect/rendering.py scripts/planimation_phase1.py
```

Observed focused fixture result: `34 passed`. The cache/image field receipt is recorded in `.omo/evidence/phase3-task-3-render-cache.json`.
