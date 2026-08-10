# Task Plan: Phase 3 Pilot Rendering and Replay Alignment

## Goal
Validate the frozen pilot bindings, render or resumably checkpoint all 16,822 canonical missing states through an approved digest-bound path, audit coverage, and prepare digest-bound alignment input for the 790 replay-plan rows without creating off-plan action targets or Qwen rows.

## Phases
- [x] Phase 1: Confirm HEAD, branch, working tree, protected paths, and required skills.
- [x] Phase 2: Read the required evidence and audit renderer, cache, manifest, state-hash, and resumability contracts.
- [x] Phase 3: Validate source-index, materialization, request, coverage, and immutable-input bindings.
- [x] Phase 4: Add only required adapters under RED/GREEN tests, or reuse the approved renderer unchanged.
- [ ] Phase 5: Execute resumable rendering and record exact progress, failures, duplicates, collisions, and resume command. (Blocked after the authorized one-state remote smoke failed.)
- [ ] Phase 6: Rerun coverage, bind accepted PNG bytes, and prepare replay-only alignment input for all authoritative replay rows.
- [x] Phase 7: Run focused and regression tests, Ruff, basedpyright, digest/collision checks, immutable comparisons, staged secret scan, and independent code review.
- [ ] Phase 8: Update resolved plan status and durable findings, commit only this milestone with the honest RED count, and push normally.

## Hard Boundaries
- Do not infer an off-plan action target, create Qwen rows, or force off-plan events into `planning_cgas_v1` without a newer owner-approved policy.
- Do not create `planning_vlm/`, load model weights, train, run the production selector/corpus loop, create checkpoint 2, mutate either characterization root, delete v2 bytes, or change release digest `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`.
- Use `source ~/cd_vlaplan` for every Python command and install nothing.
- Preserve pre-existing untracked `.omo/` paths and unrelated files.

## Required Bindings
- Source index: 31,171 rows = 790 replay-plan + 30,381 off-plan-only; SHA-256 `46d1e7c1c0a6a133372782e691888840a74f3d3732dd625b5e2d8611fdf5d390`.
- Canonical missing request: 16,822 unique states; SHA-256 `13db7cba5fb1cf885bd203ff657e5c7714bda6f832c5970dbfe5a9dee36d0585`.
- Initial accepted render coverage: 0.

## Decisions Made
- Audit and reuse an approved renderer before considering new implementation.
- Treat rendering and off-plan action selection as separate concerns; the unresolved action policy does not block rendering.
- Stop only at full coverage or an exact deterministic resumable checkpoint.
- Authoritative Planimation source and the official API client prove the current endpoint, multipart field names, and no-filename encoding are correct; do not make a speculative client change.
- The exact server error proves the request reached Planimation's planner invocation and its downstream solver returned neither `ok` nor `PENDING`; it does not distinguish service availability from solver-side PDDL compatibility. Retain the authorized-operator command rather than adding a fallback.
- The frozen state-only request has no canonical source-candidate binding. Fail before network use when repeated same-state index rows differ in candidate/source identity; do not select a goal by incidental index order.
- Owner approved the explicit representative mapping on 2026-08-10 with policy `replay_then_held_out_then_stable_source_v1`; mapping publication remains local-only and does not change frozen request/index bytes.

## Errors Encountered
- Shell replacement of the pre-existing planning files was denied by the safety classifier; switched to dedicated exact file edits after reading both files.
- The first smoke-input extraction used `jq 'first'` against a JSONL stream, which applies `first` per input and failed; use a bounded Python JSONL reader under `source ~/cd_vlaplan` instead.
- A local diagnostic initially queried nonexistent `PDDLTask.objects` and failed with `AttributeError`; the independent parser/solver check used the supported task interface and established 8 objects, 5 goals, 144 grounded actions, and a four-step solution.
- The first durable root-cause evidence write omitted the required `file_path` tool argument and was rejected before any file change; it was rerun with the explicit evidence path.
- A broader Ruff/basedpyright probe included unchanged legacy Planimation client/test files and exposed one pre-existing import-order diagnostic plus pre-existing type diagnostics. `git diff` confirms those files are untouched; the scoped milestone Ruff and basedpyright gates pass.
- One scoped basedpyright command was temporarily denied because the safety classifier was unavailable; retry succeeded with 0 errors, 0 warnings, and 0 notes.
- Independent review invalidated the assumption that a state digest selects one source problem: 4,293 requested states span distinct candidates and 4,282 span distinct goals. Added a RED test reproducing first-row selection, then a GREEN fail-fast source-identity check; no remote request was made.
- An attempted adapter CLI preflight was correctly denied because the command text retained the external endpoint and could transmit repository data. No bypass was attempted; the RED/GREEN unit test proves the source-identity failure occurs before renderer invocation.

## Status
**Blocked in Phase 5** - the explicit 16,822-row representative mapping is materialized and adapter-bound under policy `replay_then_held_out_then_stable_source_v1`; mapping SHA-256 is `3d6ff222e3662319d9429e18e3bd0d33a7ea1aee67a07e6d9b1a25c506ad7de3`. It makes one render source explicit for every frozen request state while preserving the request/index bytes and reporting 4,282 distinct-goal ambiguity groups; it does not remove that ambiguity. The remaining blocker is the separately controlled remote Planimation boundary: the prior authorized one-state smoke failed and no fresh external request is authorized in this mapping pass. Production rendering and the 790-row replay alignment remain unstarted. No commit or push has occurred.
