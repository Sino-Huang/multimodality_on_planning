# CGAS 12-Object Production Smoke Certification

## Authorization

The repository owner authorized the exact run proposed in the immediately preceding interactive question:

- issue: `https://github.com/Sino-Huang/multimodality_on_planning/issues/7`
- owner interactive answer: `Authorize exact run (Recommended)`
- output root: `/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-12-object-production-smoke-20260817-attempt-001`
- port: `18081`
- fixture config: `configs/cgas/planimation_smoke/12-object.json`
- execution limit: one authorized Attempt
- authorization record: `.claude/evidence/cgas-phase3-pilot-rendering/authorization-20260817-12-object-production-smoke-attempt-001.json`
- authorization timestamp: `2026-08-17T13:23:43+10:00`
- authorization preceded execution: `true`

The preflight confirmed that the output root was absent and port `18081` was unbound before execution.

## Execution

The authorized Attempt used:

```bash
source ~/cd_vlaplan && python .claude/evidence/cgas-phase3-pilot-rendering/local_planimation_adapter_integration.py --output-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-12-object-production-smoke-20260817-attempt-001 --fixture 12-object --port 18081
```

The first launch completed successfully and produced the following success output:

```text
Conda environment 'ada_vla' is already activated.
backend listening on http://127.0.0.1:18081
SUCCESS: proof-report.json written
```

The bounded smoke performed Render Production (VFG and PNG), followed by Render Validation and Integration Certification. The retained Evidence Bundle records one POST to `http://127.0.0.1:18081/upload/pddl`, with `hosted_requests=0` and loopback-only project-client network evidence. No retry, hosted request, fallback, 8-object smoke, 16,822-state production-corpus render, replay alignment, or corpus release occurred.

## Procedural disclosure

After the successful authorized Attempt, the execution lane incorrectly invoked the adapter a second time solely while trying to capture an exit code. It exited `2` at the pre-existing output-root guard:

```text
ERROR: --output-root must not exist: /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-12-object-production-smoke-20260817-attempt-001
```

The second invocation did not start a backend, issue any HTTP request, or write or modify evidence. There were two adapter process invocations, but only one authorized domain Attempt and exactly one retained/backend-observed POST. No further adapter invocation occurred.

## Certification result

`proof-report.json` records `status: success` and `certified: true`. All eight named claims pass:

- `backend_commit_match`: `pass`
- `expected_action_sequence_match`: `pass`
- `loopback_plan_submission`: `pass`
- `no_hosted_client_request`: `pass`
- `render_artifacts_valid`: `pass`
- `render_counts_exact`: `pass`
- `semantic_validation_pass`: `pass`
- `vfg_action_sequence_match`: `pass`

The expected, submitted, and VFG Action Sequences are identical:

```text
(stack b10 b9)
```

Adapter counts are exactly `requested=1`, `processed=1`, and `succeeded=1`, with `failed=0`, `duplicate=0`, `collision=0`, and `remaining=0`. The semantic receipt records `status: success`, `14/14` covered sprites, and `1024x1024` PNG dimensions.

The retained PNG is:

`/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-12-object-production-smoke-20260817-attempt-001/state_cache/blocksworld/ca6fb5aa595c065744e0172f1b50d4e237bd4c851d094de684127a240cd3e85d/db6c4749c7c4a3d3eea04fab8a3a6790/frames/frame_000.png`

Its SHA256 digest is `1a669cc78e9486c2b1b4be6dc66ed0d634daf731b5c4d9995ea3dcfd226989b7`.

The retained VFG trace is:

`/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-12-object-production-smoke-20260817-attempt-001/state_cache/blocksworld/ca6fb5aa595c065744e0172f1b50d4e237bd4c851d094de684127a240cd3e85d/db6c4749c7c4a3d3eea04fab8a3a6790/trace.vfg.json`

Its SHA256 digest is `b018a4908ef0366b569f5b106b7d25644fc13e8cef2147e4b86363caa54ef955`.

The offline verifier was run once after the smoke and exited `0`:

```bash
source ~/cd_vlaplan && python -m scripts.phase3.cgas_planimation_evidence verify --attempt-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-12-object-production-smoke-20260817-attempt-001
```

It independently reported `certified: true` and all eight claims passing.

## Resource bounds

- adapter request timeout: `90` seconds
- backend startup timeout: `180` seconds
- maximum attempts: `1`
- request delay: `0` seconds
- fixture object count: `12`
- expected action count: `1`
- expected visual stage count: `2`
- rendered visual stage count: `2`
- minimum object coverage: `0.01`
- request count: `1`
- hosted requests: `0`

## Retained evidence

The complete Evidence Bundle contains `15` regular files totaling `105314` bytes, including:

- `proof-report.json` and `backend.log`
- `fixture/index.jsonl` and `fixture/request.jsonl`
- `diagnostics/run-contract.json`, `diagnostics/state_render_manifest.jsonl`, and `diagnostics/render-checkpoint.jsonl`
- `reports/render-report.json`
- the deterministic profile and candidate problem PDDL
- the derived problem PDDL, Planimation-compatible problem PDDL, `result.json`, VFG trace, and rendered PNG

The generated output root is retained unchanged as evidence for this single 12-object localhost smoke Attempt. The committed report and diagnostics preserve host-specific absolute paths as provenance, so the retained Evidence Bundle is host-bound; the offline verifier remains the direct validation path when the retained Attempt root is available.

## Validation

Completed evidence:

- preflight: output root absent and port `18081` unbound before execution
- adapter success: first launch completed successfully, backend listening, proof report written
- offline certification verifier: run once after the smoke, exit `0`, `certified: true`, all eight claims `pass`
- focused tests: `source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_planimation_evidence.py tests/phase3/test_planimation_smoke_fixtures.py tests/phase3/test_local_planimation_adapter_integration.py tests/phase3/test_cgas_pilot_planimation_adapter.py tests/test_planimation_phase1.py` -> `133 passed in 1.32s`
- focused basedpyright over `scripts/planimation_phase1_client.py`, `scripts/phase3/planimation_pairing_contracts.py`, `scripts/phase3/planimation_pairing_rendering.py`, `scripts/phase3/cgas_pilot_planimation_adapter.py`, `scripts/phase3/cgas_planimation_evidence.py`, and `.claude/evidence/cgas-phase3-pilot-rendering/local_planimation_adapter_integration.py` -> `0 errors, 0 warnings, 0 notes`
- full suite: `source ~/cd_vlaplan && python -m pytest -q tests` ran once and stopped during collection with `13 errors in 11.51s` plus `1 unrelated warning`; two tests cannot import `receipt_path` from `tests/phase3/organize_outputs_support.py`, eleven cannot import `VIEW_ROOT` from `scripts/phase3/output_layout_contracts.py`; exactly matches documented pre-existing baseline, none of the failing files/modules are changed by issue #7, and no required workflows exist under `.github/workflows/`

## Review

The mandatory two-axis review inspected the staged issue #7 diff against fixed point `7608d62`:

- Standards: no findings
- Spec: no findings

The Spec interpretation follows `CONTEXT.md`: an Attempt is one authorized immutable execution with its own identity and retained outcome. The second output-root-guard-rejected process did not become a second domain Attempt because it created no identity or evidence, started no backend, issued no request, and mutated nothing.

Residual risk: a colloquial process-level reading of execution could treat the second invocation as exceeding the recorded execution limit, even though the repository domain contract supports the one-Attempt conclusion.
