# Phase 3 F2 Image and Rollout Remediation

F2 reproduced two failures: texture-only images could satisfy sprite coverage, and promotion was not bound to the frozen manifest, full selected rows, or prior receipt artifacts. The semantic gate now derives object contrast from the local perimeter around each expected sprite, so gradients, grids, and deterministic noise do not constitute object coverage. Valid fixture object semantics remain unchanged.

Promotion now freezes complete pairing rows, compares the current manifest SHA-256 and every selected row identity, records a canonical receipt SHA-256, and validates the immediately preceding receipt plus its recorded artifact hashes. Missing selection/output artifacts produce a rejected receipt with stable reasons and empty unavailable hashes rather than an uncaught file error.

No active source root, planner behavior, release verifier, or real canary was changed. Active-source rollout remains blocked by legacy trace-contract versions.

## Verification Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_render_semantics.py tests/phase3/test_rollout_gates.py tests/phase3/test_verify_planimation_vlm.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/render_semantics.py scripts/phase3/rollout_gates.py tests/phase3/test_render_semantics.py tests/phase3/test_rollout_gates.py tests/phase3/test_verify_planimation_vlm.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/render_semantics.py scripts/phase3/rollout_gates.py tests/phase3/test_render_semantics.py tests/phase3/test_rollout_gates.py tests/phase3/test_verify_planimation_vlm.py
```

Observed results: 15 focused tests passed, basedpyright reported zero diagnostics, and compilation exited zero. The corrective evidence is `.omo/evidence/phase3-f2-image-rollout-remediation-2026-07-16.json`.
