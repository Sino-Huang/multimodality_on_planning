# Successor-prediction held-out comparison closeout (#99)

Goal 9 Phase 3 ran the frozen model-predicted versus trusted-successor comparison
on the qualified fallback coverage: all 3 development tasks plus the 12
outcome-blind selected unseen tasks (one minimum exact-reference-cost task per
domain), across all three modalities and both arms — 90 episodes, complete
coverage, zero missing bindings.

Published evidence: [successor-evaluation.json](successor-evaluation.json) is
byte-identical to the audited runtime artifact
`outputs/expanded-study/v1/successor/evaluation/evidence.json`
(sha256 `32af278df87f9c0a…`). Episode journals, raw predictions and replay
records follow the repository's local outputs convention and are not Git assets.

## Results

Trusted successor arm (authority transition, no model calls): 45/45 episodes
reached the goal — 3/3 development and 12/12 unseen per modality, as expected
for canonical BFS over solvable tasks.

Model-generated successor arm (strictly verified predictions; rejection
terminates the episode as `invalid_successor` with no trusted replacement):

| Panel | Modality | Success | Model calls | Accepted | Schema | Effect | Static context |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| development | text-state | 0/3 | 7 | 4 | 1 | 2 | 0 |
| development | visual-state | 0/3 | 7 | 4 | 1 | 2 | 0 |
| development | multimodal-state | 0/3 | 7 | 4 | 1 | 2 | 0 |
| unseen | text-state | 0/12 | 29 | 17 | 2 | 10 | 0 |
| unseen | visual-state | 0/12 | 33 | 21 | 7 | 5 | 0 |
| unseen | multimodal-state | 1/12 | 26 | 15 | 4 | 6 | 1 |

The single model-arm success is unseen `expanded-final/elevators-compact-914002`
(multimodal-state). 109 model calls were used of the 4,062 allowance
(2 × 677 exact-reference decisions × 3 modalities); most episodes terminate on
the first rejected prediction, so the allowance was never approached. This is a
measured outcome, not reduced coverage.

Compared with the untrained starting adapters' fixed-query collection (Goal 8:
1,274/1,536 schema failures), the trained successor adapters rarely fail schema
(16 schema failures of 109 predictions) but still fail exact whole-state
identity/effects often enough that downstream canonical BFS usually terminates
before the goal. Per-check validity (schema, static context, source identity,
action identity, applicability, state identity, effect), downstream search,
model calls and compute are reported separately in the evidence; no predicted
state was ever repaired or replaced by a trusted state
(`trusted_state_substitutions = 0` in every episode), and all 109 raw
predictions are retained.

## Provenance and the disclosed audit repair

Four-stage runtime lineage: training at `dd4818a`; episode production at
`59fb882`; replay-verifier fix at `7456808`; re-audit and finalization at
`7f1f893`.

The attempt-1 scheduler audit hooks failed (returncode 1) because the
independent replay verifier omitted the live driver's terminating
`next_request()` call, so naturally terminated episodes replayed one expansion
short with the goal undetected (46/90 episodes: all 45 trusted plus the one
goal-reaching model episode). No recorded episode changed; the defect was in
the verifier only. The fix added the terminating call plus regression tests.
Because the scheduler refuses relaunch after a succeeded worker, each attempt
directory now also retains a `reaudit-result.json`: a passing standalone
re-audit under `7f1f893` that embeds the original failed hook receipt. The
published evidence discloses both `hook_returncode: 1` and the re-audit summary
for every worker attempt. Re-audit validation binds schema, worker,
job/attempt/directory, outcome, complete coverage and the embedded original
receipt; it does not prove timestamp ordering or commit ancestry, and the
evidence does not claim otherwise. Finalization and `audit-final` each
independently replayed all 90 episodes from the retained raw records under the
fixed verifier and matched the published evidence exactly.

## Accounting

`successor-evaluate-0` (GPU 0, port 18800): 0.389697 GPU-hours;
`successor-evaluate-1` (GPU 1, port 18801): 0.251746 GPU-hours;
`successor-evaluate-final` CPU-only. Evaluation consumed 0.641443 GPU-hours;
successor branch cumulative 10.851129 / 64. Active episode wall time 2,113.7 s;
model-call wall time 2,043.9 s. One attempt per job; no retries; the CPU
finalizer job succeeded with hook returncode 0.

## Verification

Read-only verification of the published evidence (does not modify any
artifact):

```bash
source ~/cd_vlaplan
EXPANDED_TERMINAL_PATH=outputs/expanded-study/v1/jobs/successor-evaluate-final/1/terminal.json \
  python scripts/run_expanded_successor_evaluation.py audit-final
```

`audit-final` independently recomputes the complete evidence from retained
episodes and requires byte equality with the published report.

The following commands are mutating repair/republication operations, not
read-only checks: `audit-worker` refreshes each attempt's
`independent-replay.json` (and `reaudit-result.json` on pass) with the current
runtime head and timestamp, and `finalize` republishes `evidence.json`. Running
them after publication therefore produces artifacts that differ from this
committed byte-identical copy; use them only for a deliberate republication.

## Limitations

- Fallback coverage (12 unseen tasks, one per domain) was the frozen
  outcome-blind admission; the full 24-task panel was projected infeasible in
  Goal 7 and is explicitly missing by design, not dropped after outcomes.
- One training seed (17) per cell; no training-seed variance is claimed.
- Model-arm downstream success is measured under canonical BFS action order
  with a 2× exact-reference call limit; it is not a claim about other search
  algorithms or policies.
