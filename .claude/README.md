# `.claude/` — project working state

This directory replaced `.omo/` and `.sisyphus/` on 2026-08-07. It is the authoritative home for
plans, knowledge, the work ledger, and load-bearing evidence. It is tracked in git; only
`archive/` is ignored.

## Start here

| Path | What it is |
| --- | --- |
| `production-p0-status.md` | Fastest orientation on the current CGAS corpus work: state, digests, standing constraints. |
| `plans/production-p0-corpus-experiment-readiness.md` | The approved production plan. Partly superseded — see below. |
| `../doc/high_level_plans/research_execution_plan.md` | The research plan, revision 2. **Read this before planning any new work.** |
| `../doc/research_proposal.md` | The ICLR 2027 proposal the execution plan serves. |
| `knowledge/` | 20 current notes, carried verbatim. |
| `knowledge/ARCHIVE-INDEX.md` | The other 98 notes, with where each one's content lives now. |
| `ledger.jsonl` | Append-only work ledger, 39 entries across 5 plans. **Never rewrite prior lines.** |
| `evidence/` | Load-bearing evidence only — see below. |
| `archive/` | Tarball of the full pre-migration evidence tree. Gitignored. |

## Current state, in one paragraph

The production P0 corpus is blocked at Todo 4 of the production plan, but the block has been
diagnosed and ruled on. The owner took four decisions on 2026-08-07 (raise IW to true iterative
width 1→2; drop three redundant BFS snapshot fields from persistence; drop starVLA and reduce to
three VLM backbones; re-derive corpus scale from experiment needs), and the research execution plan
was rewritten as revision 2 to match. Parts of the production plan are therefore superseded — the
disposition table is in the research execution plan. The recommended next action is the Phase A
probe, which needs no approval.

## `evidence/` — what is here and why

Only two categories were carried over. Everything else is in the tarball.

**Load-bearing — referenced by live code. Do not move without updating the referrer.**

| Path | Referenced by |
| --- | --- |
| `cgas-production-p0/` | `tests/phase3/cgas_candidate_characterization_support.py:24-26` |
| `cgas-partition-characterization/planning_cgas_v1-draft.json` | `scripts/phase3/cgas_planner_blocker_probe.py:24` |
| `task-4-cgas-dataloader-and-experiment-support/fixture/` | `tests/phase3/test_cgas_qwenvl_conversion.py:17` |
| `planimation-pilot-contract-and-render-recovery/…/{ferry,elevators}-failed-attempt/` | `tests/phase3/test_planimation_profile_regressions.py:13-14` |

`cgas-production-p0/approved-trace-v2.json` is the **owner approval artifact** for the trace-v2
contract. It was untracked and gitignored under `.omo/`; it is now tracked. It cannot be regenerated
by a worker.

**Re-runnable and still cited by the research plan.**

`production-p0-corpus-experiment-readiness/task-4/` holds the selector infeasibility proof and the
owner decision packet, each with read-only scripts that reproduce their outputs:

```bash
source ~/cd_vlaplan
E=.claude/evidence/production-p0-corpus-experiment-readiness/task-4/selector-infeasibility-proof
bash "$E/capture-preconditions.sh"        # six read-only precondition checks
python "$E/derive_infeasibility.py"       # reproduces proof.json byte-identically

P=.claude/evidence/production-p0-corpus-experiment-readiness/task-4/owner-decision-packet
python "$P/measure_corpus_eligibility.py"
python "$P/measure_trace_event_growth.py"
python "$P/derive_quota_options.py"
```

All were verified to work from this location after the migration.

## Recovering anything that was removed

| You want | Where to look |
| --- | --- |
| An archived knowledge note | `knowledge/ARCHIVE-INDEX.md` names the maintained write-up or the git path for all 98 |
| A completed-phase plan | `git show <rev>:.omo/plans/<name>.md` — all 7 were tracked |
| Raw evidence from a completed phase | `tar -xzf .claude/archive/omo-evidence-2026-08-07.tar.gz` (1,307 files, verified byte-exact) |
| Working notes, drafts, research syntheses | `git show <rev>:.omo/notepads/…`, `.omo/drafts/…`, `.omo/ulw-research/…` — all tracked |

`<rev>` is the commit immediately preceding the 2026-08-07 removal.

**Not carried over, deliberately:** `.omo/run-continuation/` (1,226 session-state files),
`.omo/teams/`, `.omo/lazycodex-executor-verify/`, and both `boulder.json` files. These are
orchestration state for a retired tool, not project knowledge. All were tracked except where noted,
so they remain in git history.

## Conventions

- The ledger is append-only. Add lines; never edit or reorder existing ones.
- `doc/` holds durable, curated write-ups. `.claude/knowledge/` holds working notes. When a note
  matures, promote it to `doc/` rather than letting the two drift.
- Evidence scripts under `.claude/evidence/` are deliberately outside `scripts/phase3/` and carry no
  RED/GREEN TDD obligation. Anything under `scripts/phase3/` does.
