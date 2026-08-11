# Phase 3 Pilot Rendering Verification - 2026-08-11 - Canonicalized 8-object Smoke (v3)

## Outcome

Overall acceptance FAIL. The owner authorized exactly one repository-derived canonicalized
mapping-bound 8-object request to the hosted Planimation backend. The adapter made exactly one
canonical request, which was persisted as failed. No VFG, no PNG, and no semantic receipt were
produced. The remote boundary remains red; the state-cache result fields for trace/frame/vfg/png/
semantic are empty. Decision: remain RED.

## Authorization and Exact Execution

- Owner authorized exactly one repository-derived canonicalized mapping-bound 8-object request to
  `https://planimation.planning.domains/upload/pddl`.
- Preflight passed.
- Exactly one request was made:
  - `--timeout-seconds 30`, `--request-delay-seconds 0`, `--max-attempts 1`;
  - canonical endpoint only, no fallback;
  - new output root
    `outputs/image_frames/cgas-phase3-pilot-planimation-adapter-smoke-v3-canonical-8obj-20260811`.
- No retry and no remediation were performed.
- Process exit 0 because the adapter persists failed results.

Command stdout (exact JSON):

```json
{"counts": {"collision": 0, "duplicate": 0, "failed": 1, "processed": 1, "remaining": 1, "requested": 1, "succeeded": 0}, "manifest_path": "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-phase3-pilot-planimation-adapter-smoke-v3-canonical-8obj-20260811/diagnostics/state_render_manifest.jsonl", "report_path": "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-phase3-pilot-planimation-adapter-smoke-v3-canonical-8obj-20260811/reports/render-report.json"}
```

Counts are exact: requested 1, processed 1, succeeded 0, failed 1, duplicate 0, collision 0,
remaining 1.

## Persisted Failure

Exact persisted remote failure message (verbatim):

```
Failed to submit PDDL bundle. Attempts: https://planimation.planning.domains/upload/pddl -> API error: The process ends with an exception \n\n Unexpected status from the server
```

Overall acceptance FAIL: no VFG, no PNG, no semantic receipt. State-cache result fields are empty
for trace/frame/vfg/png/semantic.

## Binding/Artifact Validation

- Source identity: state `00014e0bdfd513580c65f03b94e5c0a1487c34c7be37bd1fadf92bf9643e5f7f`; row
  `cgas-pilot-expansion-20b7ac18577176c1fa927b68`; candidate
  `0322c69e499f0e2ba7161d25787a1260a275bd22382438a7f48e51e9da3737c4`; object_count 8, raw_rank 93,
  bfs/train, replay false.
- Source SHA: `37d284f8b8b34c5a9b351092734ed663169e8191408044a6337d645a33e66198`.
- Mapping SHA: `e7703cb4faf05b69496dd244b545ee7171ab37f5abc419dad3d4af30059bb4bd`.
- Run-contract self-bound SHA:
  `2b5776d18458dbd37899c1496c775197228c2acd66be0f190e51e9a2c58d4b88`.
- All request/index/mapping/domain/profile/manifest/checkpoint/implementation digests matched.

## Frozen-Input and Git Integrity

- Frozen internal problem: 489 bytes, SHA `f5e8e79e7c594b2ffa83906825016d7c368893abb3b1009dea277d367b81daa9`;
  b00..b07 identities preserved.
- Submitted compat problem: 430 bytes, SHA `ca23d3def6ea76e4a45b8a12f159459c8d4bfdcad5862fe317a2b45b681fe5ff`;
  exact b1..b8 bijective semantic rename and July formatting.
- Full frozen request/index/mapping/report/manifest counts and digests remained unchanged, as did all
  six immutable inputs.
- Current Git porcelain is byte-identical to preflight; no unrelated changes were introduced.

## Final Local Gates

Run once, all passed:

- `40 passed in 0.46s`
- Ruff: `All checks passed!`
- basedpyright: `0 errors, 0 warnings, 0 notes`

## Interpretation (confidence labels)

Evidence observation: the submitted compat PDDL differs from the successful replay-3 problem by only
the problem-name line; the naming/formatting hypothesis is therefore not sufficient. Suspected cause:
problem-name sensitivity or hosted-backend nondeterminism (confidence: medium). Causality is NOT
claimed.

## Boundaries and Next Gate

- 12-object smoke: not run.
- Production 16,822 render: not started.
- Replay alignment / Qwen / planning_vlm / training: not run.
- No off-plan action was inferred.
- Next gate: a future remote probe requires new explicit authorization. No retry is proposed in this
  session.
