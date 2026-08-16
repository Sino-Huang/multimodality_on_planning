# CGAS 4-Object Localhost Integration Certification

## Authorization

The repository owner approved the exact run proposed in the immediately preceding interactive message:

- issue: `https://github.com/Sino-Huang/multimodality_on_planning/issues/4`
- output root: `/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-local-adapter-integration-20260816-attempt-002`
- port: `18322`
- execution limit: exactly one fixture-bound attempt
- authorization record: `.claude/evidence/cgas-phase3-pilot-rendering/authorization-20260817-local-adapter-integration-attempt-002.json`

The preflight confirmed that the output root did not exist, port `18322` was not listening, the isolated backend interpreter was executable, and the read-only backend clone was at approved commit `94d82afb5ee122ce579dd11ca1953b7c85ca5824` before execution.

## Execution

The following command was run exactly once:

```bash
source ~/cd_vlaplan && python .claude/evidence/cgas-phase3-pilot-rendering/local_planimation_adapter_integration.py \
  --output-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-local-adapter-integration-20260816-attempt-002 \
  --backend-python /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python \
  --port 18322
```

It exited `0` after one HTTP `200` POST to `http://127.0.0.1:18322/upload/pddl`. The harness terminated the backend and released port `18322`. No retry, alternate root, alternate port, hosted request, fallback, 8/12-object smoke, or production render occurred.

The earlier failed run at `outputs/image_frames/cgas-local-adapter-integration-20260812-attempt-001` was not reused, resumed, or modified.

## Certification result

`proof-report.json` records `status: success`, `certified: true`, and all eight claims passing:

- `expected_action_sequence_match`
- `loopback_plan_submission`
- `backend_commit_match`
- `vfg_action_sequence_match`
- `render_artifacts_valid`
- `semantic_validation_pass`
- `render_counts_exact`
- `no_hosted_client_request`

The normalized expected, submitted, and VFG Action Sequences all equal `[(pickup b1)]`. Adapter counts are exactly `requested=1`, `processed=1`, `succeeded=1`, with `failed=0`, `duplicate=0`, `collision=0`, and `remaining=0`. The semantic receipt records a `1024×1024` PNG with all six VFG sprites covered.

The shared verifier independently re-read the retained report and artifacts and exited `0` with `certified: true` and the same eight passing claims:

```bash
source ~/cd_vlaplan && python -m scripts.phase3.cgas_planimation_evidence verify \
  --attempt-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-local-adapter-integration-20260816-attempt-002
```

## Retained evidence

The complete 67 KiB run root is retained, including:

- `proof-report.json`
- `backend.log`
- `fixture/index.jsonl` and `fixture/request.jsonl`
- `diagnostics/run-contract.json`
- `diagnostics/state_render_manifest.jsonl`
- `diagnostics/render-checkpoint.jsonl`
- `reports/render-report.json`
- deterministic profile and derived problem PDDL
- VFG trace, rendered PNG, and per-render `result.json`

The output remains a synthetic 4-object localhost certification only. It does not authorize the separately gated 8-object smoke, 12-object smoke, 16,822-state production render, replay alignment, or corpus release.

## Focused validation

Before execution:

- focused verifier, harness, adapter, and forwarding tests: `105 passed`
- focused basedpyright: `0 errors, 0 warnings, 0 notes`
- focused Ruff: `All checks passed!`
