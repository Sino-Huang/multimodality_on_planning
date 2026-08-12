# Task Plan: Phase 3 Pilot Rendering and Replay Alignment

## Goal
Validate the frozen pilot bindings, render or resumably checkpoint all 16,822 canonical missing states through an approved digest-bound path, audit coverage, and prepare digest-bound alignment input for the 790 replay-plan rows without creating off-plan action targets or Qwen rows.

## Phases
- [x] Phase 1: Confirm HEAD, branch, working tree, protected paths, and required skills.
- [x] Phase 2: Read the required evidence and audit renderer, cache, manifest, state-hash, and resumability contracts.
- [x] Phase 3: Validate source-index, materialization, request, coverage, and immutable-input bindings.
- [x] Phase 4: Add only required adapters under RED/GREEN tests, or reuse the approved renderer unchanged. The representative-mapping binding was committed as `f9a5081` and pushed to `origin/main`.
- [ ] Phase 5: Execute resumable rendering and record exact progress, failures, duplicates, collisions, and resume command. (Blocked after both the 2026-08-10 smoke and the 2026-08-11 mapping-bound smoke failed at the remote downstream planner boundary.)
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
**Red - repository-side remote compatibility delta proven; backend selection resolved 2026-08-12.** The representative-mapping milestone is committed as `f9a5081` and pushed to `origin/main`. On 2026-08-11 four separately authorized regression replays ran against the canonical endpoint (one attempt, zero delay, new output roots; exact July-22 known-good problem, exact smoke-v2 actually-transmitted problem, canonicalized pilot delta, and 12-object empty-goal probe). Replay 1 (July-22 known-good) SUCCEEDED, refuting a blanket upstream regression/outage; replay 3 (same pilot semantics, `b00..b07→b1..b8` + July formatting) SUCCEEDED; replay 2 (exact smoke-v2 transmitted problem) FAILED with the byte-identical downstream error from 2026-08-10 (`API error: The process ends with an exception / Unexpected status from the server`); replay 4 (12-object empty-goal) FAILED later at stage generation (`Failed to generate stages \n\n 'init'`). The replay 2→3 pair proves a repository-side remote compatibility delta in the problem writer; the compound probe changed BOTH object naming and formatting, so neither alone is claimed causal. Replay 4 does NOT prove 12-object incompatibility — empty-goal handling failed, object count is not isolated. The adapter/problem-writer canonical `b1..bN` naming + July-compatible formatting patch is now COMPLETE, tested, reviewed, and integrated (`b9e2e65`, Ruff closure `020b812`); do not reopen it. On 2026-08-12 the owner selected the pinned local backend (commit `94d82afb5ee122ce579dd11ca1953b7c85ca5824`, v0.1.7) as the production backend target for the two required smokes ONLY, and approved the local digest/provenance contract (local bytes are not expected to match hosted bytes) and the GPL-separated maintainability model. Remaining before any render: validate the integrated adapter/`StateRenderer` against localhost, then pass the mapping-bound 8-object AND a 12-object non-empty locally solvable representative-goal smoke through the localhost production path with full VFG→PNG→semantic/digest/provenance validation (one bounded execution path, no hosted request or fallback) — these smokes are defined in prose only and require separate execution authorization. Production 16,822-state rendering and the 790-row replay alignment remain unstarted; coverage is 0/16,822. Full record: `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260811-regression-replays.md`.

## Continuation Session — 2026-08-11
- [x] SG0: Verify the July known-good and August smoke-v2 bundle hashes; stage four immutable replay inputs under `tmp/` without network access.
- [x] SG1: Run four separately authorized, single-attempt, zero-delay requests on new output roots: July verbatim, smoke-v2 verbatim, canonicalized pilot, and 12-object empty-goal probe.
- [x] Decision: Classify the evidence as upstream regression, repository-side problem-writer delta, or a valid-smoke path. Do not start production unless a mapping-bound smoke is fully valid.
- [ ] Finalize: Record exact evidence, run end-of-session verification once, then commit/push only on pass; on failure create a local `wip:` commit and handoff without pushing. **Blocked:** the first final checksum command failed because it ran from the repository root instead of the checksum manifest's staging directory. Per policy it was not rerun; no tests, commit, or push followed.

**Current continuation status:** SG0 PASS, SG1 COMPLETE (4/4 replays run), Decision COMPLETE as
**RED — repository-side remote compatibility delta**. Replay 1 (July-22 known-good verbatim)
succeeded with trace SHA `8c3b2eaf…4da00` (72,261 bytes); replay 3 (canonicalized pilot: same
semantics, `b00..b07→b1..b8` + July formatting) succeeded with trace SHA `337b9885…c1c64` (20,655
bytes); replay 2 (smoke-v2 actually-transmitted verbatim) and replay 4 (12-object empty-goal probe)
failed with exact persisted exceptions (`The process ends with an exception / Unexpected status
from the server` and `Failed to generate stages \n\n 'init'` respectively). This refutes a blanket
upstream regression (replay 1 succeeds today) and proves a repository-side delta; the compound
probe changed BOTH naming and formatting, so neither alone is claimed causal. Replay 4 does NOT
prove 12-object incompatibility (empty-goal stage-generation failure, not object-count failure);
12-object compatibility remains unproven. Production 16,822-state rendering and 790-row replay
alignment remain unstarted. Finalize FAILED at its first command: `sha256sum -c tmp/cgas-phase3-planimation-regression-replays-20260811/SHA256SUMS` returned exit 1 because its relative entries were resolved from the repository root. The failure was recorded verbatim and not rerun; no tests, commit, or push occurred. Full record: `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260811-regression-replays.md`
and `.handoff/2026-08-11-cgas-phase3-planimation-replay-classification.md`. The operator command
must not be authorized/resumed until the writer patch plus both required smokes pass.

## Local Planimation Backend Proof Session — 2026-08-11

### Goal
Prove or hard-stop a pinned, GPL-separated local upstream Planimation backend through replay-3 repeat determinism, VFG-to-PNG semantic validation, empty-plan behavior, and one representative 12-object non-empty-goal validation without hosted requests, adapter integration, or production rendering.

### Evidence Path
- [x] LP0: Verify current handoff assumptions, Git baseline, authority-plan dependency, and exact local assets.
- [x] LP1: Clone `planimation/backend` under `.slim/clonedeps/repos/`, pin exact commit `94d82afb5ee122ce579dd11ca1953b7c85ca5824` (`v0.1.7`), preserve its GPL-3.0 license, and record source metadata without vendoring project code.
- [x] LP2: Inspect supplied-plan handling and prepare an isolated environment. The seven hermetic upstream tests are scheduled for final verification; the eighth upstream test is excluded because its source makes a hosted solver request.
- [x] LP3: Start only a loopback backend process with a supplied local plan and no external planner use. **Technically complete (attempt-002):** the loopback backend started with `hosted_requests: 0` per `outputs/image_frames/loop-msp0by7b-4ommsi-attempt-002-final-verification/proof-report.json`.
- [x] LP4: Submit the exact replay-3 bundle twice; compare VFG bytes and, if different, record exact semantic/envelope/color deltas. Parse VFG, extract one PNG, and pass existing semantic validation. **Technically complete (attempt-002):** replay-3 local run1/run2 raw bytes matched SHA `363c41eb…`; VFG→PNG semantic validation passed.
- [x] LP5: Probe empty-plan behavior, then validate one local 12-object non-empty-goal representative with a supplied local plan. **Technically complete (attempt-002):** the empty plan was rejected via planner routing; the representative 12-object non-empty-goal VFG→PNG semantic validation passed.
- [x] LP6: Run final verification once. Command 1 failed during test-module import; exact output is preserved and no remediation was applied.
- [ ] LP7: Finalize Git according to pass/fail policy and write `.handoff/2026-08-11-cgas-local-planimation-proof-{success|failure}.md` with the exact next dependency-ready action.

### Hard Stops
- Exact project domain/problem/profile rejected beyond a small reviewable upstream patch.
- Supplied-plan path absent or invokes an external planner.
- Dependency runtime cannot be isolated reproducibly.
- GPL-separated aggregation is not maintainable.
- Replay-3 VFG is nondeterministic/unpinnable or semantic validation fails.

### Session Boundaries
- No hosted API request, no 12-object hosted request, no adapter integration, no production render, no replay alignment, no Qwen/planning_vlm/training, and no fallback implementation.
- Stop and record the first hard-stop condition without switching to fallback B.

### Status
**Session GREEN — LP3/LP4/LP5 technically complete (attempt-002); not authorization.** The loopback supplied-plan backend started with `hosted_requests: 0`; replay-3 local run1/run2 raw bytes matched SHA `363c41eb…`; PNG semantic validation passed; the empty plan was rejected via planner routing; and the representative 12-object non-empty-goal VFG→PNG semantic validation passed (see `outputs/image_frames/loop-msp0by7b-4ommsi-attempt-002-final-verification/proof-report.json` and the attempt-002 handoff). Technical completion is distinct from authorization: the production 16,822-state render, the 790-row replay alignment, and the operator command remain unauthorized and unstarted. Exact output: `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260811-local-planimation-backend-proof.md`.

## Local Planimation Backend Proof Resume — 2026-08-11

- [x] LR0: Verify prior handoff, project HEAD, clone pin, and command-local `PYTHONPATH` import.
- [x] LR1: Run exactly seven hermetic upstream tests; all seven passed and hosted-solver `test_planimation_process` remained excluded.
- [ ] LR2: Run loopback proof through replay-3 determinism, PNG semantics, empty-plan, and 12-object validation. **Blocked before startup:** harness resolved the venv interpreter symlink to base Conda Python, which lacks Django.
- [x] LR3: Stop at the first formal verification failure and preserve exact evidence without remediation.
- [ ] LR4: Commit failure evidence locally, write a separate failure handoff commit, and do not push.

**Resume status — LR2 block superseded; proof completed technically in attempt-002 (not authorization).** The venv-interpreter block was resolved by the pinned local venv (`.slim/clonedeps/.venv-planimation-v0.1.7`), and the loopback proof through replay-3 determinism, PNG semantics, empty-plan rejection via planner routing, and 12-object non-empty-goal validation completed with `hosted_requests: 0`. No hosted request or production action occurred. Exact evidence: `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260811-local-planimation-backend-proof-resume.md` and `outputs/image_frames/loop-msp0by7b-4ommsi-attempt-002-final-verification/proof-report.json`.

## Local Planimation Determinism Investigation — 2026-08-12

### Goal
Resolve the replay-3 VFG color nondeterminism with one small, reviewable change outside the pinned GPL clone, while preserving the byte-for-byte determinism hard stop, then resume the local-only proof through PNG semantics, empty-plan behavior, and one 12-object non-empty-goal validation.

### Evidence Path
- [x] LD0: Trace the pinned backend's sprite/color construction and reconcile it with the two persisted replay-3 VFG artifacts.
- [x] LD1: Add the smallest outside-clone deterministic control and focused regression coverage; do not normalize or weaken the VFG comparison.
- [x] LD2: Run final verification once: focused coverage followed by one fresh proof through replay-3, PNG semantics, empty-plan, and 12-object validation, stopping at the first hard stop. **Technically complete (attempt-002):** focused verification was 14 passed, Ruff passed, and the fresh proof exited 0 per `outputs/image_frames/loop-msp0by7b-4ommsi-attempt-002-final-verification/proof-report.json`.
- [x] LD3: Finalize Git according to pass/fail policy and write the required handoff with the exact next dependency-ready action. Completed by implementation/closure commit `9a6bb13409d8cc04548929762385f5fdf536b3b9` and `.handoff/2026-08-12-cgas-local-planimation-loop-attempt-002-success.md`.

### Hard Boundaries
- Do not edit `.slim/clonedeps/repos/planimation__backend/`.
- Make no hosted request, do not start production, and do not add fallback behavior.
- Do not proceed past any hard-stop condition.

### Status
**Session GREEN — LD2 and LD3 complete (attempt-002); not authorization.** The harness materializes only the exact `RANDOMCOLOR` sentinel to concrete `GREY` in memory after source hash verification; the pinned clone, on-disk input, backend process, and raw VFG byte-equality hard stop remain unchanged. Focused verification was 14 passed, Ruff passed, and the fresh proof exited 0: replay-3 local run1/run2 raw bytes matched SHA `363c41eb…`; PNG semantic validation passed; the empty plan was rejected via planner routing; and the representative 12-object non-empty-goal VFG→PNG semantic validation passed. Git/handoff closure is recorded by commit `9a6bb13409d8cc04548929762385f5fdf536b3b9` and `.handoff/2026-08-12-cgas-local-planimation-loop-attempt-002-success.md`; production authorization remains ungranted. Exact output: `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260812-local-planimation-determinism-fix.md` and `outputs/image_frames/loop-msp0by7b-4ommsi-attempt-002-final-verification/proof-report.json`.

## Backend Selection Decision — 2026-08-12

- Owner answered the decision-packet question with **Pinned local backend** on 2026-08-12.
- Selected target: pinned local `planimation/backend` commit `94d82afb5ee122ce579dd11ca1953b7c85ca5824` (`v0.1.7`), ONLY for the two required production-path smokes and for later consideration, not authorization, of a separate 16,822-state pilot render.
- Rulings recorded: (1) exact commit approved; (2) local digest/provenance contract approved — pinned commit, reproducible isolated runtime, supplied-plan behavior, profile materialization, VFG/PNG digests, semantic receipts, local bytes not expected to match hosted bytes; (3) GPL-separated maintainability approved — read-only clone, isolated runtime, no vendoring/editing clone in the MIT repo, explicit pin/update/environment ownership; (4) future localhost validation of the integrated adapter/`StateRenderer` authorized only.
- The mapping-bound 8-object and representative non-empty-goal 12-object localhost production-path smokes are defined in prose only and are NOT executed or authorized in this session; separate execution authorization is required.
- Stop on missing governance evidence or first smoke failure. Even if both pass, only prepare a separate owner/operator decision for the 16,822-state render; do not authorize it here.
- Coverage remains 0/16,822; no render, replay alignment, release, model, or training started. The hosted production command remains NOT EXECUTABLE and superseded as the selected backend path; no executable localhost command was created.
- Record: `.claude/evidence/cgas-phase3-pilot-rendering/backend-selection-decision-packet-20260812.md`.
