# Phase 3 CGAS Qwen-VL Conversion

`scripts/phase3/cgas_qwenvl.py` converts only rows accepted by Todo4 `verify_steps()` into deterministic native Qwen JSONL. It sorts each split by `step_id`, copies exactly one regular non-symlink PNG per accepted step to `images/<split>/<step_id>.png`, validates its Todo4 alignment digest before copy, preflights a complete candidate, and atomically publishes only verified output.

The persisted manifest binds exact source, alignment, steps, and Todo4 `steps_manifest.json` digests; per-split count, IDs, and JSONL digest; and every copied image relative path and byte digest. Verification strictly parses JSONL objects, requires canonical annotation bytes, derives the exact expected image set from accepted records, and rejects orphan PNGs, non-PNG files, extra directories/files, symlinks, missing images, stale inputs, split leaks, duplicates, and manifest drift. Failed rebuilds leave the prior approved output intact.

2026-07-28 status: production `data/planning_cgas_v1` contained only the schema at Todo 5 time. The accepted 12-row inputs were fixture artifacts, so generated QA output was retained only under `.omo/evidence/task-5-cgas-dataloader-and-experiment-support/qa/`; no fixture rows were promoted to the production Qwen path by Todo 5.

2026-07-31 current status: Todo 6 supersedes that publication status. The fail-closed release gate accepted 12 emitted rows through source, alignment, steps, Qwen conversion, strict loader preflight, and native loader smoke checks, then published `data/planning_cgas_v1/release_manifest.json` with SHA-256 `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`. That release manifest is the only authorized CGAS handoff for downstream work. It does not claim live memory, route labels or calibration, CGAS training or implementation, or attention analysis as delivered.

Commands used:

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_qwenvl_contracts.py tests/phase3/test_cgas_qwenvl_publication.py tests/phase3/test_cgas_qwenvl_conversion.py tests/phase3/test_cgas_certificates.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_qwenvl.py tests/phase3/test_cgas_qwenvl_conversion.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_qwenvl --verify --source-root .omo/evidence/task-5-cgas-dataloader-and-experiment-support/qa/source --alignment-root .omo/evidence/task-5-cgas-dataloader-and-experiment-support/qa/alignment --corpus-root .omo/evidence/task-5-cgas-dataloader-and-experiment-support/qa/corpus
```
