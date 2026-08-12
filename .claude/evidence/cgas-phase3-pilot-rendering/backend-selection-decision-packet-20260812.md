# Backend Selection Decision Packet — 2026-08-12

## Current Authority State

Per the owner-provided current authority state for this decision, the adapter/problem-writer compatibility work is complete. Canonical `b1..bN` naming and July-compatible problem formatting are implemented, tested, and integrated into the adapter's default production path by implementation commit `b9e2e65` and Ruff closure commit `020b812` in:

- `scripts/phase3/cgas_pilot_planimation_adapter.py`;
- `tests/phase3/test_cgas_pilot_planimation_adapter.py`.

Accordingly, the owner's explicit current-state instruction supersedes the older wording in `doc/high_level_plans/research_execution_plan.md` that lists the writer patch as the next unfinished gate. The next unresolved gate is selection of the backend for the two required production-path smokes.

Production coverage remains **0/16,822**. No production render, 790-row replay alignment, pilot release, model implementation, or training has started. The command in `.claude/evidence/cgas-phase3-pilot-rendering/operator-command.md` remains non-executable.

Backend approval and production-render authorization are separate decisions. Selecting a backend authorizes neither the 16,822-state render nor transmission of the full production request.

## Decision Requested

The owner is asked to select either hosted Planimation or the pinned local backend for the required production-path smokes. If both smokes pass, any consideration of the 16,822-state pilot render must return for separate explicit authorization. The exact owner question appears at the end of this packet.

## Hosted Planimation Assessment

### Evidence established

- The exact July known-good replay succeeded against `https://planimation.planning.domains` on 2026-08-11, refuting a blanket service outage or regression.
- Canonicalized replay 3 also succeeded with the pilot semantics preserved.
- The mapping-bound canonicalized 8-object smoke-v3 failed with `Unexpected status from the server`; no VFG, PNG, or semantic receipt was produced.
- The smoke-v3 submitted problem and successful replay 3 differed only in the problem-name line.
- Problem-name sensitivity remains unresolved. Hosted-backend nondeterminism is also possible, and causality has not been established.
- The required non-empty-goal 12-object production-path smoke has not passed.

Evidence: `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260811-regression-replays.md` and `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260811-canonicalized-8obj-smoke-v3.md`.

### Evidence still required if hosted is selected

1. Obtain separate authorization for exactly the two repository-derived hosted smoke requests; this does not authorize production rendering.
2. Run the mapping-bound canonicalized 8-object smoke through the integrated adapter and `StateRenderer` production path, with one attempt, no retry, and no fallback.
3. Run the representative non-empty-goal 12-object smoke through the same path and constraints.
4. Require both smokes to complete VFG→PNG generation and semantic validation, with accepted VFG/PNG digests and complete backend, endpoint, input, mapping, and implementation provenance.
5. Resolve or bound the unexplained problem-name/hosted-behavior sensitivity sufficiently to justify accepting successful smoke receipts as production-path evidence. A further unexplained failure leaves the hosted branch blocked.
6. After both smokes pass, record an explicit evidence disposition for the unresolved problem-name/hosted-behavior sensitivity: either establish its cause or define an owner-accepted operational bound showing why the successful production-path receipts are sufficient. Without that disposition, the hosted branch remains blocked.
7. Only after both smokes pass and the sensitivity disposition is accepted, prepare a separate owner/operator decision on whether to authorize the digest-bound resumable 16,822-state render.

## Pinned Local Backend Assessment

### Evidence established

- The inspected backend is pinned to `planimation/backend` commit `94d82afb5ee122ce579dd11ca1953b7c85ca5824` (`v0.1.7`). The GPL dependency clone remains separate and was not edited.
- The supplied-plan loopback proof completed with `hosted_requests: 0`.
- Replay-3 local runs were byte-identical with SHA-256 `363c41eb…`.
- PNG semantic validation passed.
- Empty plans were rejected through planner routing rather than being accepted as supplied plans.
- The representative 12-object non-empty-goal VFG→PNG semantic proof passed.
- Local and hosted VFG digests differ. The recorded differences include color behavior, so hosted digests cannot be reused as the local acceptance baseline.
- This was a supplied-plan technical proof. It was not a localhost adapter/`StateRenderer` production-path smoke and is not production authorization.

Evidence: `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260812-local-planimation-determinism-fix.md` records the first stopped verification sequence; its result is superseded by the accepted attempt-002 evidence in `.handoff/2026-08-12-cgas-local-planimation-loop-attempt-002-success.md` and `outputs/image_frames/loop-msp0by7b-4ommsi-attempt-002-final-verification/proof-report.json`.

### Decisions and evidence still required if local is selected

1. Owner approval of the pinned local commit as the production backend target for the required smokes.
2. An explicit local digest/provenance contract defining the accepted backend commit, environment, supplied-plan behavior, profile materialization, VFG/PNG digests, semantic receipts, and the fact that local output is not expected to match hosted bytes.
3. A GPL-separated maintainability ruling covering operation of the read-only dependency clone, reproducible environment ownership, update/pinning responsibility, and the prohibition on vendoring or editing the clone in this MIT project.
4. Validation that the integrated adapter and `StateRenderer` operate correctly against localhost, without hosted requests or fallback.
5. A mapping-bound 8-object production-path smoke and a representative non-empty-goal 12-object production-path smoke through that localhost adapter/`StateRenderer` path, each passing VFG→PNG semantic, digest, and provenance validation.
6. Only after both smokes pass, prepare a separate owner/operator decision on whether to authorize the digest-bound resumable 16,822-state render.

## Comparison and Recommendation

| Dimension | Hosted Planimation | Pinned local backend |
|---|---|---|
| Demonstrated reliability | July known-good replay and canonicalized replay 3 succeeded. | Supplied-plan loopback, repeated replay 3, PNG semantics, empty-plan routing, and representative non-empty-goal 12-object proof succeeded. |
| Unresolved failures | The mapping-bound canonicalized 8-object production-path smoke failed despite differing from successful replay 3 only by the problem-name line; cause remains unknown. The required 12-object smoke is unpassed. | No failure remains in the bounded supplied-plan technical proof, but the actual localhost adapter/`StateRenderer` production path is unvalidated. |
| Determinism | Not established for the required production path; the replay-3/smoke-v3 outcome difference remains unexplained. | Replay-3 repeats were byte-identical at SHA-256 `363c41eb…` after the project-owned deterministic profile control. |
| Network and data-transmission exposure | Each smoke and any later render transmits repository-derived domain, problem/state, and profile data to the hosted service. | Loopback validation can run with `hosted_requests: 0`, avoiding external transmission and network availability dependence. |
| Digest and provenance | Existing hosted receipts remain useful, but successful replay-3 bytes do not predict smoke-v3 success. Endpoint/service implementation provenance is not locally pinned. | Backend source is pinned, but local output has a distinct digest family, including color differences; a new local acceptance and provenance contract is required. |
| Licensing and maintenance | No local GPL runtime maintenance, but the project depends on an externally operated service and its unpinned runtime behavior. | Requires an explicit GPL-separated operating model, reproducible environment ownership, and maintenance of the pinned external clone without editing or vendoring it. |
| Work before both required smokes | The adapter writer is already complete. Two hosted production-path smokes remain, plus a defensible treatment of the unresolved problem-name/behavior sensitivity. | Backend/provenance/GPL rulings and localhost adapter/`StateRenderer` validation precede the same two production-path smokes. |
| Risk of wasting further effort | Higher near-term diagnostic risk: another request may reproduce the unexplained hosted failure without identifying a controllable cause. | Higher governance/integration setup cost, but lower technical uncertainty once the localhost production path is connected to the already deterministic pinned proof. |

### Recommendation

**Recommend selecting the pinned local backend for the remaining production-path validation, subject to explicit owner approval of the backend, local digest/provenance contract, and GPL-separated maintenance model.**

This recommendation is based on the available evidence: the local branch has already demonstrated byte-identical replay behavior, successful PNG semantic validation, correct empty-plan routing, and a successful representative non-empty-goal 12-object proof without network transmission. The hosted branch has successful regression replays, but its only mapping-bound canonicalized production-path smoke failed for an unresolved reason after the writer compatibility patch was applied to that request. Repeating hosted attempts before the cause is bounded has a greater risk of consuming authorization and diagnostic effort without advancing the production gate.

The recommendation does not convert the supplied-plan proof into an adapter-path smoke, does not resolve the local provenance or GPL-maintenance decisions, and does not authorize production rendering. The final backend selection remains the owner's decision.

## Branch-Specific Continuation

### If hosted is selected

The exact next milestone is: **separately authorize and execute only the mapping-bound canonicalized 8-object smoke and then the representative non-empty-goal 12-object smoke through the hosted integrated adapter/`StateRenderer` production path, with one attempt per smoke, no retry or fallback, and full VFG→PNG→semantic/digest/provenance acceptance; if both pass, record and obtain owner acceptance of the problem-name/hosted-behavior sensitivity disposition.**

If either smoke fails, stop and record the evidence; do not start the 16,822-state render. If both pass but the sensitivity remains neither causally resolved nor operationally bounded to the owner's satisfaction, remain blocked. Only after both passes and an accepted disposition may a new, separate production-render authorization packet be prepared.

### If the pinned local backend is selected

The exact next milestone is: **record owner approval of the pinned backend plus the local digest/provenance contract and GPL-separated maintainability ruling; then validate the integrated adapter/`StateRenderer` against localhost and execute only the mapping-bound 8-object and representative non-empty-goal 12-object production-path smokes, with no hosted request or fallback and full VFG→PNG→semantic/digest/provenance acceptance.**

If any governance ruling or smoke fails, stop and record the evidence; do not start the 16,822-state render. If both smokes pass, prepare a new, separate production-render authorization packet.

## Session Boundaries

This packet records evidence and requests an owner decision only. This session did not run hosted or localhost smokes, start production rendering, perform replay alignment, generate a corpus, release the pilot, implement a model, or start training. It did not edit the pinned GPL dependency clone and does not reinterpret the successful local technical proof as production authorization.

Which backend is approved for the required production-path smokes and, if those smokes pass, consideration of a later separately authorized 16,822-state pilot render: hosted Planimation or the pinned local backend?
