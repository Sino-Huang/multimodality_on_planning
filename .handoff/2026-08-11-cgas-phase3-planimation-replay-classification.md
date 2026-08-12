# Handoff — 2026-08-11 CGAS Phase 3 Planimation Replay Classification

## Completed

- Staged four immutable replay bundles and an inert single-POST harness at
  `tmp/cgas-phase3-planimation-regression-replays-20260811/` (27-file `SHA256SUMS` verified;
  `bundle.json` provenance, `command.txt` per bundle, `expected/` artifacts).
- Ran all four separately authorized, single-attempt, zero-delay replays against
  `https://planimation.planning.domains/upload/pddl` on new output roots under
  `outputs/image_frames/cgas-phase3-planimation-regression-replay-01..04-20260811/`.
  - Replay 1 (exact July-22 known-good): **success**, trace SHA `8c3b2eafb14a39a2cb4c4b820d05bb281874793a6ee12e7327f648faaa54da00` (72,261 bytes).
  - Replay 2 (exact smoke-v2 actually-transmitted): **failed** (exception persisted; see Failures).
  - Replay 3 (canonicalized pilot delta): **success**, trace SHA `337b988571ba3127c4d8a63fc99e2ea2fb77938d6e30bef95bf0199350dc1c64` (20,655 bytes).
  - Replay 4 (12-object empty-goal probe): **failed** (exception persisted; see Failures).
- Classified the evidence: RED — repository-side remote compatibility delta (blanket upstream
  regression refuted; see Suspected Root Cause).
- No code patch was made in this session. No commit was created because final verification failed
  before staging; commit hash: `none`.
- Evidence written: `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260811-regression-replays.md`
  (new), `.claude/evidence/cgas-phase3-pilot-rendering/operator-command.md` (warning added; command
  itself unchanged), `task_plan.md` (SG0/SG1/Decision complete, Finalize in progress),
  `notes.md` (outcomes appended), `doc/high_level_plans/research_execution_plan.md` (Immediate Next
  Step 8 unblock replaced).

## Failures

The harness persists application failures into `result.json` and exits normally (code 1) without
printing the exception to stdout, so each failing replay's full shell stdout is exactly the conda
activation banner. Each failing command, its full actual shell stdout, and the full persisted
`result.json` contents follow.

### Replay 2 — exact smoke-v2 actually-transmitted problem

Command:

```bash
source ~/cd_vlaplan && python /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/harness/replay_planimation_client.py --domain-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-02-failing-smoke-v2-verbatim/domain.pddl --problem-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-02-failing-smoke-v2-verbatim/problem.pddl --profile-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-02-failing-smoke-v2-verbatim/blocksworld_AP.pddl --output-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-phase3-planimation-regression-replay-02-20260811 --pddl-url https://planimation.planning.domains/upload/pddl --timeout-seconds 30 --max-attempts 1 --request-delay-seconds 0
```

Full actual shell stdout (verbatim):

```
Conda environment 'ada_vla' is already activated.
```

Full `outputs/image_frames/cgas-phase3-planimation-regression-replay-02-20260811/result.json` (verbatim):

```json
{
  "status": "failed",
  "url": "https://planimation.planning.domains/upload/pddl",
  "inputs": {
    "domain": {
      "path": "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-02-failing-smoke-v2-verbatim/domain.pddl",
      "sha256": "2eed94c5a8fdfe2ac608c45cdf8a68274d69c1920bb4f831529f7bfaaaf79d81",
      "bytes": 1002
    },
    "problem": {
      "path": "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-02-failing-smoke-v2-verbatim/problem.pddl",
      "sha256": "f5e8e79e7c594b2ffa83906825016d7c368893abb3b1009dea277d367b81daa9",
      "bytes": 489
    },
    "profile": {
      "path": "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-02-failing-smoke-v2-verbatim/blocksworld_AP.pddl",
      "sha256": "9ded071f7ae255de719d753a815bf56ed6756393e14a6065a331e7d5297a8d32",
      "bytes": 9368
    }
  },
  "output": null,
  "exception": {
    "type": "RuntimeError",
    "text": "Failed to submit PDDL bundle. Attempts: https://planimation.planning.domains/upload/pddl -> API error: The process ends with an exception \n\n Unexpected status from the server"
  }
}
```

### Replay 4 — 12-object empty-goal probe

Command:

```bash
source ~/cd_vlaplan && python /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/harness/replay_planimation_client.py --domain-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-04-12obj-empty-goal/domain.pddl --problem-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-04-12obj-empty-goal/problem.pddl --profile-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-04-12obj-empty-goal/blocksworld_AP.pddl --output-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-phase3-planimation-regression-replay-04-20260811 --pddl-url https://planimation.planning.domains/upload/pddl --timeout-seconds 30 --max-attempts 1 --request-delay-seconds 0
```

Full actual shell stdout (verbatim):

```
Conda environment 'ada_vla' is already activated.
```

Full `outputs/image_frames/cgas-phase3-planimation-regression-replay-04-20260811/result.json` (verbatim):

```json
{
  "status": "failed",
  "url": "https://planimation.planning.domains/upload/pddl",
  "inputs": {
    "domain": {
      "path": "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-04-12obj-empty-goal/domain.pddl",
      "sha256": "2eed94c5a8fdfe2ac608c45cdf8a68274d69c1920bb4f831529f7bfaaaf79d81",
      "bytes": 1002
    },
    "problem": {
      "path": "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-04-12obj-empty-goal/problem.pddl",
      "sha256": "a4376855d9f032efbdcb6db2bbf13505b39fa741e30ab0290f5d2a963a48bb64",
      "bytes": 429
    },
    "profile": {
      "path": "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-planimation-regression-replays-20260811/bundle-04-12obj-empty-goal/blocksworld_AP.pddl",
      "sha256": "9ded071f7ae255de719d753a815bf56ed6756393e14a6065a331e7d5297a8d32",
      "bytes": 9368
    }
  },
  "output": null,
  "exception": {
    "type": "RuntimeError",
    "text": "Failed to submit PDDL bundle. Attempts: https://planimation.planning.domains/upload/pddl -> API error: Failed to generate stages \n\n 'init'"
  }
}
```

### Final verification — checksum invocation from the wrong working directory

Command:

```bash
sha256sum -c tmp/cgas-phase3-planimation-regression-replays-20260811/SHA256SUMS
```

Exit code: `1`.

Full actual stdout/stderr (verbatim):

```text
sha256sum: bundle-01-july-verbatim/blocksworld_AP.pddl: No such file or directory
sha256sum: bundle-01-july-verbatim/bundle.json: No such file or directory
sha256sum: bundle-01-july-verbatim/command.txt: No such file or directory
sha256sum: bundle-01-july-verbatim/domain.pddl: No such file or directory
sha256sum: bundle-01-july-verbatim/expected/result.json: No such file or directory
sha256sum: bundle-01-july-verbatim/problem.pddl: No such file or directory
sha256sum: bundle-02-failing-smoke-v2-verbatim/blocksworld_AP.pddl: No such file or directory
sha256sum: bundle-02-failing-smoke-v2-verbatim/bundle.json: No such file or directory
sha256sum: bundle-02-failing-smoke-v2-verbatim/command.txt: No such file or directory
sha256sum: bundle-02-failing-smoke-v2-verbatim/domain.pddl: No such file or directory
sha256sum: bundle-02-failing-smoke-v2-verbatim/expected/result.json: No such file or directory
sha256sum: bundle-02-failing-smoke-v2-verbatim/expected/state_render_manifest.jsonl: No such file or directory
sha256sum: bundle-02-failing-smoke-v2-verbatim/problem.pddl: No such file or directory
sha256sum: bundle-02-failing-smoke-v2-verbatim/reference/NOT_TRANSMITTED.txt: No such file or directory
sha256sum: bundle-02-failing-smoke-v2-verbatim/reference/candidate_problems/00014e0bdfd513580c65f03b94e5c0a1487c34c7be37bd1fadf92bf9643e5f7f.pddl: No such file or directory
sha256sum: bundle-03-canonicalized-pilot-delta/blocksworld_AP.pddl: No such file or directory
sha256sum: bundle-03-canonicalized-pilot-delta/bundle.json: No such file or directory
sha256sum: bundle-03-canonicalized-pilot-delta/command.txt: No such file or directory
sha256sum: bundle-03-canonicalized-pilot-delta/domain.pddl: No such file or directory
sha256sum: bundle-03-canonicalized-pilot-delta/problem.pddl: No such file or directory
sha256sum: bundle-04-12obj-empty-goal/blocksworld_AP.pddl: No such file or directory
sha256sum: bundle-04-12obj-empty-goal/bundle.json: No such file or directory
sha256sum: bundle-04-12obj-empty-goal/command.txt: No such file or directory
sha256sum: bundle-04-12obj-empty-goal/domain.pddl: No such file or directory
sha256sum: bundle-04-12obj-empty-goal/problem.pddl: No such file or directory
sha256sum: harness/replay_planimation_client.py: No such file or directory
sha256sum: WARNING: 26 listed files could not be read
bundle-01-july-verbatim/blocksworld_AP.pddl: FAILED open or read
bundle-01-july-verbatim/bundle.json: FAILED open or read
bundle-01-july-verbatim/command.txt: FAILED open or read
bundle-01-july-verbatim/domain.pddl: FAILED open or read
bundle-01-july-verbatim/expected/result.json: FAILED open or read
bundle-01-july-verbatim/problem.pddl: FAILED open or read
bundle-02-failing-smoke-v2-verbatim/blocksworld_AP.pddl: FAILED open or read
bundle-02-failing-smoke-v2-verbatim/bundle.json: FAILED open or read
bundle-02-failing-smoke-v2-verbatim/command.txt: FAILED open or read
bundle-02-failing-smoke-v2-verbatim/domain.pddl: FAILED open or read
bundle-02-failing-smoke-v2-verbatim/expected/result.json: FAILED open or read
bundle-02-failing-smoke-v2-verbatim/expected/state_render_manifest.jsonl: FAILED open or read
bundle-02-failing-smoke-v2-verbatim/problem.pddl: FAILED open or read
bundle-02-failing-smoke-v2-verbatim/reference/NOT_TRANSMITTED.txt: FAILED open or read
bundle-02-failing-smoke-v2-verbatim/reference/candidate_problems/00014e0bdfd513580c65f03b94e5c0a1487c34c7be37bd1fadf92bf9643e5f7f.pddl: FAILED open or read
bundle-03-canonicalized-pilot-delta/blocksworld_AP.pddl: FAILED open or read
bundle-03-canonicalized-pilot-delta/bundle.json: FAILED open or read
bundle-03-canonicalized-pilot-delta/command.txt: FAILED open or read
bundle-03-canonicalized-pilot-delta/domain.pddl: FAILED open or read
bundle-03-canonicalized-pilot-delta/problem.pddl: FAILED open or read
bundle-04-12obj-empty-goal/blocksworld_AP.pddl: FAILED open or read
bundle-04-12obj-empty-goal/bundle.json: FAILED open or read
bundle-04-12obj-empty-goal/command.txt: FAILED open or read
bundle-04-12obj-empty-goal/domain.pddl: FAILED open or read
bundle-04-12obj-empty-goal/problem.pddl: FAILED open or read
harness/replay_planimation_client.py: FAILED open or read
```

The command was run from the repository root, while `SHA256SUMS` contains paths relative to its own
staging directory. Per session policy, no corrected rerun, tests, staging, commit, or push followed.

## Suspected Root Cause

- **Repository problem-writer combined naming/format delta — confidence: high.** Replay 2 (the
  exact smoke-v2 transmitted problem, `b00..b07` naming, non-July formatting) fails while replay 3
  (identical semantic init/goal with `b1..b8` naming and July formatting) succeeds against the same
  endpoint, domain, and profile. The remote planner boundary is not blanket-broken (replay 1 also
  succeeds today).
- **Inability to isolate naming vs formatting — confidence: high.** The replay 2→3 probe changed
  BOTH object naming and problem formatting together; no single-axis probe was run, so neither
  change alone is claimed causal.
- **12-object compatibility unresolved — confidence: high.** Replay 4 failed at stage generation
  (`Failed to generate stages \n\n 'init'`) on an empty goal, which does not isolate object count;
  12-object compatibility with a non-empty goal remains unproven.
- **Final checksum verification failure was invocation-context error — confidence: high.** The
  checksum manifest paths are relative to the staging root, but the command ran from the repository
  root. This does not invalidate the earlier independent SG0 checksum PASS; it blocks this session's
  finalization because the failed command was not rerun.

## Next Session Options

- **Option A:** Implement the canonical writer patch — canonical `b1..bN`
  naming and July-compatible problem formatting under RED→GREEN tests — then independent code
  review and focused/regression/Ruff/basedpyright gates. After that, run two separately authorized
  mapping-bound smokes: a canonicalized 8-object smoke and a 12-object smoke with a non-empty
  locally solvable representative goal, each requiring full VFG→PNG→semantic/digest/provenance
  validation. Production 16,822-state rendering starts only after both smokes pass.
- **Option B (recommended):** First rerun the failed checksum verification from
  `tmp/cgas-phase3-planimation-regression-replays-20260811/` as a fast-fail gate, then proceed with
  Option A only if it passes.

**Recommendation: Option B.** The verification correction is local, deterministic, and cheap; it
should clear the recorded session-finalization failure before implementation begins. Replay 2→3
still gives the subsequent writer patch a concrete GREEN target and regression guard.
