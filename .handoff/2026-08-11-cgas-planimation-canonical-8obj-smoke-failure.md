# Handoff — 2026-08-11 CGAS Planimation Canonical 8-Object Smoke Failure

## Completed

- All handoff assumptions were checked against the current working tree, `main`, and `origin/main`; preflight passed. `main`/`origin/main`/HEAD initially equaled `bec48d768cb94c30bb1409b93300ec7bdf1490dd`; unrelated dirt was preserved.
- Exactly one owner-authorized mapping-bound 8-object request ran at the canonical endpoint `https://planimation.planning.domains/upload/pddl`, timeout 30, zero delay, `max_attempts 1`, no fallback, new output root
  `outputs/image_frames/cgas-phase3-pilot-planimation-adapter-smoke-v3-canonical-8obj-20260811`. No retry or remediation was performed.
- The local WIP evidence commit is EXACT SHA `0d287fdbba1a84c9089dfd29d781b05783fcb10e` with message `wip: record failed canonical 8-object smoke`; it was not pushed.
- Evidence: `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260811-canonicalized-8obj-smoke-v3.md`; output root as above.
- Local final gates passed: 40 adapter tests, Ruff, basedpyright; frozen inputs and Git dirty snapshot unchanged.

## Failures

The shell process exit was 0, so the failing acceptance result is the adapter's exact stdout plus the persisted remote failure, not a nonzero shell command.

Command stdout exact fenced block:

```text
Conda environment 'ada_vla' is already activated.
{"counts": {"collision": 0, "duplicate": 0, "failed": 1, "processed": 1, "remaining": 1, "requested": 1, "succeeded": 0}, "manifest_path": "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-phase3-pilot-planimation-adapter-smoke-v3-canonical-8obj-20260811/diagnostics/state_render_manifest.jsonl", "report_path": "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-phase3-pilot-planimation-adapter-smoke-v3-canonical-8obj-20260811/reports/render-report.json"}
```

Persisted remote failure exact fenced block (exact persisted string value, diff-clean JSON-escaped representation):

```text
Failed to submit PDDL bundle. Attempts: https://planimation.planning.domains/upload/pddl -> API error: The process ends with an exception \n\n Unexpected status from the server
```

The `\n\n` sequence is the exact embedded blank-line delimiter in the persisted string.

VFG absent, PNG absent, semantic receipt absent; therefore overall acceptance FAIL. Counts exact: requested 1, processed 1, succeeded 0, failed 1, duplicate 0, collision 0, remaining 1.

Git closure failure (after the draft):

Command: `git diff --cached --check`
Exit: `2`

Output exactly:

```text
.handoff/2026-08-11-cgas-planimation-canonical-8obj-smoke-failure.md:26: trailing whitespace.
```

The second output line itself ends in a space; its exact trailing space is represented as a JSON string:

```json
"+Failed to submit PDDL bundle. Attempts: https://planimation.planning.domains/upload/pddl -> API error: The process ends with an exception "
```

The first commit attempt was not made; HEAD stayed at WIP SHA `0d287fdbba1a84c9089dfd29d781b05783fcb10e`. The only remediation was this handoff formatting correction; no remote/result/code fix occurred.

## Suspected Root Cause

- Observation: compat PDDL is 430 bytes/SHA `ca23d3def6ea76e4a45b8a12f159459c8d4bfdcad5862fe317a2b45b681fe5ff` and differs from successful replay-3 only in the problem-name line; the internal b00 problem remains 489 bytes/SHA `f5e8...daa9` (`f5e8e79e7c594b2ffa83906825016d7c368893abb3b1009dea277d367b81daa9`).
- Suspected cause: problem-name sensitivity or hosted-backend nondeterminism. Confidence label: `medium`; causality is not established. No fix is proposed.

## Owner Follow-up Assessment — Local Planimation

- Conclusion: agree that further serial hosted API probing is inefficient and non-reproducible for 16,822 states. Primary route is a pinned local upstream Planimation backend (`https://github.com/planimation/backend`) run as a separate local process, with a supplied local plan so it does not call `solver.planning.domains`.
- Why: the upstream backend is current Python/Django and produces the actual VFG semantics; the repo already has VFG→PNG, semantic validation, local planners/Fast Downward, the renderer seam, and run-contract/digest binding. Local execution removes shared-service failure and latency and allows deterministic validation.
- Critical caveats: the backend is GPL-3.0 while the project is MIT, so keep it as a separately cloned/installed aggregation with the license preserved, not copied/imported into project source; pin the commit SHA; parser compatibility and RANDOMCOLOR determinism must be proven; installing the backend alone is not fully offline unless a plan is supplied; do not use stale `planimation/backend:latest`; no installation was performed in this session.
- Primary A: local upstream backend. Fallback B: project-specific Blocksworld stage-0 builder only if the upstream parser/runtime/license hard-stops; B requires a 12-object golden sample before production. Hosted route C is retired except a separately authorized spot-check, not a production route.

## Exact Next Plan Action

This is the exact next dependency-ready rendering action and is LOCAL-ONLY:

1. Use the repository's dependency-cloning workflow to clone `planimation/backend` into an ignored external-dependency workspace and pin/record an exact commit + GPL license; do not vendor it into project source.
2. Inspect the pinned source to confirm the multipart `plan` field and setup requirements; run upstream unit tests in an isolated environment/process (all Python commands still prefixed by `source ~/cd_vlaplan`; do not perturb project dependencies unnecessarily).
3. Start one local backend process at `127.0.0.1:8000` with no external planner use.
4. Reproduce the exact accepted replay-3 bundle locally using domain SHA `2eed94c5a8fdfe2ac608c45cdf8a68274d69c1920bb4f831529f7bfaaaf79d81`, problem SHA `8a27cbb59978e68e9a48a1770d7852d0ad91b33e5af98643dea578c210244549`, profile SHA `9ded071f7ae255de719d753a815bf56ed6756393e14a6065a331e7d5297a8d32`, and the known four-step plan: `(unstack b5 b6)`, `(stack b5 b4)`, `(pickup b6)`, `(stack b6 b5)`.
5. Acceptance: same input twice deterministic; VFG parses; existing local renderer extracts one PNG; semantic validation passes. Compare against replay-3 VFG SHA `337b988571ba3127c4d8a63fc99e2ea2fb77938d6e30bef95bf0199350dc1c64`/20,655 bytes. If bytes differ, record the exact semantic/envelope/color delta; byte-pinnability must be resolved before production.
6. Probe empty-plan locally; if rejected, identify a bounded local plan-supply path. Then validate one 12-object non-empty-goal representative locally before any adapter integration.
7. Only after those proofs, add a local `StateRenderer` seam and run the mapping-bound 8-object adapter smoke against localhost. Do not start the 16,822-state production render in that session.

Hard stops: exact project domain/problem/profile rejected beyond a small reviewable upstream patch; supplied-plan path absent; dependency runtime cannot be isolated reproducibly; GPL aggregation rejected; nondeterministic/unpinnable VFG or semantic failure. On hard stop, assess fallback B — do not silently switch.

Boundaries restated: no hosted request without fresh authorization; no 12-object hosted smoke; no production render; no replay alignment/Qwen/planning_vlm/training; no off-plan target inference.

## Next Session Prompt

```text
Read .handoff/2026-08-11-cgas-planimation-canonical-8obj-smoke-failure.md first. Follow its Exact Next Plan Action: perform only the local Planimation backend proof through replay-3 determinism/VFG→PNG/semantic validation and one local 12-object validation. Pin the upstream commit, preserve GPL separation, supply a local plan, make no hosted API request, do not start production, and stop/record any hard-stop condition without fallback.
```
