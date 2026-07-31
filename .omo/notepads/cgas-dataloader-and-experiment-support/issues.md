# Issues — cgas-dataloader-and-experiment-support

Problems and gotchas encountered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## 2026-07-28T00:14:30Z

- Required baseline command has two pre-existing out-of-scope failures: missing `outputs/planning_artifacts/dataset_smoke/language.jsonl`, and duplicate `robotwin` data-registry names in DOMINO and Robotwin configs. Phase 3 pipeline tests pass; no registry or generated data artifacts were modified.

## 2026-07-28T00:24:00Z

- Reviewer gate rejected Todo 1 (`needs-fix`): removing `planner_status_summary.bfs.success_full_trace` lets the readiness CLI exit zero and publish `current_bfs_examples=0`, rather than failing with a field-specific diagnostic. Also, the plan's mandatory combined baseline remains 33 passed / 2 failed. The failures are demonstrably pre-existing but the acceptance clause has no waiver. Reviewer receipt: `.omo/evidence/task-1-cgas-dataloader-and-experiment-support/adversarial-review.json`.

## 2026-07-28T10:28:00Z

- The reviewer regression and prior registry baseline failures are remediated. A broad `tests/phase3 tests/planning_benchmark` sweep still has 19 unrelated collection errors: output-layout modules import missing `VIEW_ROOT`, organizer tests import missing `receipt_path`, and several tests cannot import `tests.phase3` support modules. These files were not modified.

## 2026-07-28T12:00:00Z

- A manually created JSONL fixture initially contained literal `\\n` delimiters due shell quoting and failed before generation with `Extra data`. Rewriting it with structural JSON rows joined by an actual newline produced the bounded candidate; no candidate output was published during the failed setup.

## 2026-07-28T12:30:00Z

- Todo 2 adversarial verification is `needs-fix`: `--verify` accepts tampered implementation/source hashes, replay IDs, limits, tie-breaks, trace versions, transition actions, stable IDs, and populated-but-fabricated IW novelty evidence. It also leaves invalid JSONLs consumable after a nonzero verification result; structural-OOD facts are metadata-only; and `_publish` loses the approved output-root name if the candidate move fails after moving the old root to `.previous`. Receipt: `.omo/evidence/task-2-cgas-dataloader-and-experiment-support/adversarial-verify.json`.

## 2026-07-28T13:30:00Z

- Todo 2 remediation review remains `needs-fix`: value-level regeneration, withdrawal, approval binding, PDDL snapshot tampering, and rollback now pass, but the generator still publishes label-only and semantic non-Blocksworld PDDL, ignores mismatched predeclared OOD object_count/horizon/composition, rejects rather than supports calibration, permits same-split duplicate IDs, and cannot create a fresh nested output parent. Superseding receipt: `.omo/evidence/task-2-cgas-dataloader-and-experiment-support/adversarial-verify-remediation.json`.

## 2026-07-28T12:18:00Z

- Independent Todo 2 completion review is `needs-fix`: a fresh manifest whose `dev` Blocksworld goal is already true generates and verifies successfully with `dev.breadth_first_search=0` and `dev.iterated_width=0` (`accepted_rows=8` overall). The generator checks only nonempty instance memberships, not the Todo 2 requirement for at least one accepted row from each planner in every split. Receipt: `.omo/evidence/task-2-cgas-dataloader-and-experiment-support/adversarial-verify-final.json`.
