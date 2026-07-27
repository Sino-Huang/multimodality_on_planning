## 2026-07-25 Work initialization
- No implementation blocker recorded yet.

## 2026-07-25 Todo 5 blocker
- [blocked] Fresh Elevators output for the exact retained state has coincident VFG sprite bounds under the unchanged semantic validator. A separate minimal profile repair plus regression evidence is required before Todo 5 can resume; do not start Todo 6.

## 2026-07-25 Todo 5 final status
- [resolved] The approved Elevators repair and one fresh Logistics canary complete all four semantic-success canaries. [pending independent review] Fresh LSP diagnostics could not complete within the harness deadline; direct basedpyright and every executable quality gate are clean.

## 2026-07-25T12:01:19Z Todo 6 runtime blocker
- [blocked] The exact first `PILOT_OUTPUT_ROOT=outputs/phase3_planimation_frames_stratified_pilot_20260725 bash temp_fast_planimation_render.sh --resume` was forcibly terminated by the execution surface after 120 seconds before it exited. Its log contains only the generator's `state_render_started` receipt; no writer remains and no exit-code receipt exists.
- [blocked] The plan's no-blind-retry fence prevents the required second invocation until this execution-timeout behavior is explicitly resolved. Consequently the first-green validations, three verifier modes, second-resume idempotence proof, and negative probes were not run.

## 2026-07-25T12:14:49Z Todo 6 semantic-failure blocker
- [supersedes timeout-only diagnosis] A persistent owned resume passed 100 states then reached 200 processed states with 5 reported failures. It was stopped at the first `semantic_image_invalid: coincident_sprite_bounds` receipt rather than retried.
- [blocked] The exact concrete failure is Ferry `ferry-dev-easy-0000`, state hash `33b9c9648b4b132c94467949b8427b34`, present in two new cache results. The four current domain profile hashes exactly equal their approved successful-canary hashes, so this is not a profile-byte regression. A separately authorized diagnosis/remediation is required before Todo 6 may resume; the three verifier modes, first-green reconciliation, second resume, and negative probes remain intentionally unrun.

## 2026-07-25 Ferry remediation verification resolution
- [resolved] The explicitly authorized final canary for state `33b9c9648b4b132c94467949b8427b34` confirmed the locally tested repair. The final profile's `location y=0` anchor and vertical car distributor yielded distinct valid car lanes, with unchanged `validate_render_artifacts()` returning `success` and `6/6` coverage.
- [not resumed] Todo 6 remains intentionally unrun. Its three verifier modes, first-green reconciliation, second resume, and negative probes still need separate authorization; this work did not mutate existing cache entries or resume the pilot.

## 2026-07-25T19:15:16Z Todo 6 idempotence evidence blocker
- [resolved] The independently approved Ferry remediation enabled two successful exact persistent resumes. The first run completed 2,568 semantic-success states with 2,058 cache hits; the second completed 2,568 semantic-success cache hits. Both launcher runs exited 0 and each completed manifest, render, and release verification. No pre-first-green cache path is missing, and the second run added no cache paths.
- [blocked] Todo 6 cannot be marked complete under its strict byte-identical requirement. The first-green and second-green hash receipts differ for `diagnostics/state_render_manifest.jsonl` and `reports/state_render_summary.json`; the latter changed from 2,058 to 2,568 cache hits. Root VLM JSONL files were not included in the first-green hash capture, so their required first-versus-second identity is unproven. Do not hand-edit generated artifacts or start Todo 7; a separately authorized contract decision/remediation is required.

## 2026-07-25T20:05:24Z Todo 6 third-resume wrapper false positive
- [pending clean-shell handoff] The first direct third-resume invocation wrote only `resume-third.log:1`, where the launcher refused before activation because `pgrep -f 'generate_planimation_vlm.*<pilot-root>'` matched the current OpenCode wrapper's prompt text. No generator or launcher process was active under executable-aware inspection; `unshare --pid --fork --mount-proc` was unavailable with `Operation not permitted`.
- The deferred runner records the launcher's raw-guard process receipts before it may invoke the exact command. If either is nonempty, it exits fail-closed and Todo 6 remains blocked; the earlier executable-aware check remains retained preflight evidence.

## 2026-07-25T20:59:12Z Todo 6 real third-run interruption
- [blocked] The detached scheduler is historical pre-launch evidence only: it failed while Conda deactivation ran under nounset. Its log is preserved unchanged. The direct exact launcher subsequently reached `state_render_finished` at 2,568 all-hit successes, then the host killed the owner at 30 minutes before the verifier loop and exit receipt.
- [blocked] The interrupted generator left `diagnostics/hybrid_output_manifest.json` non-production-complete with zero VLM-record counts. Complete warm-baseline versus post-interruption hashes differ only for that file. The missing launcher exit receipt and this substantive canonical mismatch prohibit a Todo 6 success claim or an unapproved retry.

## 2026-07-25T21:02:57Z Todo 6 replacement persistent runner
- [pending] One replacement exact resume is explicitly authorized to recover the host-interrupted launch. The new runner waits for the current wrapper to exit, rechecks both raw launcher guards, and exits fail-closed on a guard or activation failure before it may invoke the launcher.
- The prior scheduler failure, direct guard refusal, host-interrupted launcher log, incomplete hybrid manifest, and all retained cache/hash receipts remain historical evidence and are not rewritten.

## 2026-07-26T00:06:53Z Todo 6 replacement resolution
- [resolved] The authorized replacement exited 0 and restored a production-complete output. Empty canonical-path, canonical-hash, cache-path, and immutable-hash diffs against the complete second-green baseline prove byte-identical warm-cache stability; no cache entries were added or removed.
- [resolved] Structured output reconciliation found 52 selected pairs, 2,568 successful cache-hit state rows, required VLM-record totals, unchanged profiles, all three launcher verifier modes, and zero remote render attempts.

## 2026-07-26T06:11:38Z Todo 7 final status
- [resolved] The minimal rollout contract fix, cache-only fixture and changed-canary chain, three real pilot verifier modes, and one actual promotion assessment all passed.
- [resolved] The approved receipt covers the unchanged 52-pair, 2,568-state pilot and records no rejection reasons.
- [limitation] The full 2,328-pair, 537,696-state corpus remains incomplete. Todo 7 doesn't claim full-corpus completion.
