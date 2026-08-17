# CGAS 8-Object Production Smoke Certification

## Authorization

The repository owner authorized the exact run proposed in the immediately preceding interactive question:

- issue: `https://github.com/Sino-Huang/multimodality_on_planning/issues/6`
- answer: `Authorize exact run (Recommended)`
- output root: `/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-8-object-production-smoke-20260817-attempt-001`
- port: `18080`
- fixture config: `configs/cgas/planimation_smoke/8-object.json`
- execution limit: exactly one attempt
- authorization record: `.claude/evidence/cgas-phase3-pilot-rendering/authorization-20260817-8-object-production-smoke-attempt-001.json`
- authorization was recorded before execution at `2026-08-17T12:36:41+10:00`

The preflight confirmed that the output root was absent and port `18080` was unbound before execution.

## Execution

The following command was run exactly once:

```bash
source ~/cd_vlaplan && python .claude/evidence/cgas-phase3-pilot-rendering/local_planimation_adapter_integration.py --output-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-8-object-production-smoke-20260817-attempt-001 --fixture 8-object --port 18080
```

It exited `0`. Actual adapter output was:

```text
Conda environment 'ada_vla' is already activated.
backend listening on http://127.0.0.1:18080
SUCCESS: proof-report.json written
```

The retained report records one POST to `http://127.0.0.1:18080/upload/pddl`, with `hosted_requests=0` and loopback-only network evidence. No retry, hosted request, fallback, 12-object smoke, production render, replay alignment, or corpus release occurred.

## Certification result

`proof-report.json` records `status: success` and `certified: true`. All eight claims pass:

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
(unstack b5 b6)
(stack b5 b4)
(pickup b6)
(stack b6 b5)
```

Adapter counts are exactly `requested=1`, `processed=1`, `succeeded=1`, with `failed=0`, `duplicate=0`, `collision=0`, and `remaining=0`. The semantic receipt is embedded in `proof-report.json` and records `status: success`, `10/10` covered sprites, and `1024x1024` PNG dimensions.

The rendered PNG is retained at:

`outputs/image_frames/cgas-8-object-production-smoke-20260817-attempt-001/state_cache/blocksworld/0322c69e499f0e2ba7161d25787a1260a275bd22382438a7f48e51e9da3737c4/0732d6ff879af707f528a6df87cf5f0f/frames/frame_000.png`

Its SHA256 digest is `98b82ee69beedec4ba1367ebe828270cc908a8947e0a159591b06be49d365e2d`.

The VFG trace is retained at:

`outputs/image_frames/cgas-8-object-production-smoke-20260817-attempt-001/state_cache/blocksworld/0322c69e499f0e2ba7161d25787a1260a275bd22382438a7f48e51e9da3737c4/0732d6ff879af707f528a6df87cf5f0f/trace.vfg.json`

Its SHA256 digest is `12ff6e39e3b41923651fb54cceb7188c34823fb62a94d5e81f1e76d0d4a044ab`.

The shared offline verifier was run once and exited `0`:

```bash
source ~/cd_vlaplan && python -m scripts.phase3.cgas_planimation_evidence verify --attempt-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-8-object-production-smoke-20260817-attempt-001
```

It independently reported `certified: true` and the same eight claims passing.

## Resource bounds

- adapter request timeout: `90` seconds
- backend startup timeout: `180` seconds
- maximum attempts: `1`
- request delay: `0` seconds
- fixture object count: `8`
- expected action count: `4`
- expected visual stage count: `5`
- rendered visual stage count: `5`
- minimum object coverage: `0.01`
- request count: `1`
- hosted requests: `0`

## Retained evidence

The complete run root contains `15` regular files totaling `65,783` bytes, including:

- `proof-report.json` and `backend.log`
- `fixture/index.jsonl` and `fixture/request.jsonl`
- `diagnostics/run-contract.json`, `diagnostics/state_render_manifest.jsonl`, and `diagnostics/render-checkpoint.jsonl`
- `reports/render-report.json`
- the deterministic profile and candidate problem PDDL
- the derived problem PDDL, Planimation-compatible problem PDDL, `result.json`, VFG trace, and rendered PNG

The generated output root is retained unchanged as evidence for this single 8-object localhost smoke attempt.

## Validation

Completed evidence:

- preflight: output root absent and port `18080` unbound before execution
- adapter: exit `0`, proof report written
- offline certification verifier: exit `0`, `certified: true`, all eight claims `pass`
- focused tests: `source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_planimation_evidence.py tests/phase3/test_planimation_smoke_fixtures.py tests/phase3/test_local_planimation_adapter_integration.py tests/phase3/test_cgas_pilot_planimation_adapter.py tests/test_planimation_phase1.py` -> `133 passed in 1.30s`
- focused basedpyright over `scripts/planimation_phase1_client.py`, `scripts/phase3/planimation_pairing_contracts.py`, `scripts/phase3/planimation_pairing_rendering.py`, `scripts/phase3/cgas_pilot_planimation_adapter.py`, `scripts/phase3/cgas_planimation_evidence.py`, and `.claude/evidence/cgas-phase3-pilot-rendering/local_planimation_adapter_integration.py` -> `0 errors, 0 warnings, 0 notes`
- focused Ruff: non-green only for two unchanged pre-existing issue #5 diagnostics: `I001` at `local_planimation_adapter_integration.py:53` and `E501` at `cgas_planimation_evidence.py:385`; issue #6 changes only evidence/docs and does not modify those files
- full suite: `source ~/cd_vlaplan && pytest -q tests` ran once and stopped during collection with `13 errors in 12.23s` plus `1 unrelated warning`. Two tests cannot import `receipt_path` from `tests/phase3/organize_outputs_support.py`; eleven tests cannot import `VIEW_ROOT` from `scripts/phase3/output_layout_contracts.py`. These are the same pre-existing, unrelated collection errors documented in `.handoff/2026-08-17-cgas-local-adapter-integration-attempt-002-success.md`, and none of the failing modules/tests are modified by issue #6, whose changes are retained evidence and docs only.

## Review

- `[PENDING ORCHESTRATOR] code review`
