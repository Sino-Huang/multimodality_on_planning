# Phase 3 Todo 8 Release Verifier

`scripts/phase3/verify_planimation_vlm.py` now exposes explicit `manifest`, `render`, and `release` modes. The default remains `manifest`, preserving the existing manifest-only verification workflow.

`release` is fail-closed: it requires all persisted manifests, schemas, reports, and six split JSONL files; reloads every source snapshot; verifies strict hybrid records, IDs, split isolation, expected pair coverage, semantic image receipts, artifact hashes, and reconciled counts. It accepts production-complete output only.

## Verification Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_verify_planimation_vlm.py tests/phase3/test_planimation_pairing.py tests/phase3/test_render_semantics.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/verify_planimation_vlm.py tests/phase3/test_verify_planimation_vlm.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/verify_planimation_vlm.py tests/phase3/test_verify_planimation_vlm.py
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/phase3_task8_release_fixture --mode release
```

Observed results: 40 focused tests passed in 3.60 seconds, basedpyright reported no diagnostics, compilation exited zero, and the temporary release fixture reconciled one pair, two render states, one train full record, and one train step record. Evidence is at `.omo/evidence/phase3-task-8-release-verifier.json`.
