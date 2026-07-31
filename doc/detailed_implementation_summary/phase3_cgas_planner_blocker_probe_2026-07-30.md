# Phase 3 CGAS Planner Blocker Probe

## Scope

`scripts/phase3/cgas_planner_blocker_probe.py` is a diagnostic-only, read-only consumer of the frozen CGAS characterization bundle. It probes `blocksworld-dev-hard-0000`, `blocksworld-test-hard-0014`, and `blocksworld-train-hard-0000` twice with unchanged characterization limits.

## Contract

- The CLI accepts only a previously absent `tmp/cgas-planner-blocker-investigation-<token>/probe.json` target. It rejects traversal, symlinks, the CGAS state directory, evidence/draft locations, planning data, targets outside repository `tmp`, and occupied destinations.
- The canonical `probe.json` excludes timing so identical runs produce identical bytes. `timings.jsonl` separately retains wall and CPU nanoseconds for each planner and repeat.
- The record pins the final bundle, characterization member, and draft SHA-256 values before and after the probe; it also binds each source record, domain/problem PDDL, persisted `plan/sas_plan`, BFS implementation, IW implementation, replay result, full limits, statuses, counts, plan lengths, trace completeness, and disabled recovery.
- The record is explicitly `diagnostic_only: true` and `non_authoritative: true`. It contains no eligibility, approval, role, promotion, or publication field.
- Repository source files are resolved canonically only after rejecting lexical traversal and every symlinked parent component. Output is created below a `tmp` descriptor and then published through the verified newly-created evidence-directory descriptor using `O_NOFOLLOW` and `O_EXCL`, so a later pathname replacement cannot redirect either file.
- The 60-second SIGALRM limit is fresh-process-only: an active pre-existing `ITIMER_REAL` is rejected without changing its timer or handler. A handler without an active timer is restored after each planner invocation.

## Observed Evidence

Retained execution evidence: `tmp/cgas-planner-blocker-investigation-20260730t102100/`.

- Each persisted SAS plan replayed to its goal.
- Canonical BFS reached `10001` expansions with `skipped_resource_limit` for all three rows.
- Native unrecovered IW(1) exhausted novelty at 73 (dev), 71 (test), and 90 (train) expansions with `failed_no_plan_extracted` and no recovery.
- The verified bundle, characterization member, and draft SHA-256 values were identical before and after the diagnostic run.

## Hardening Evidence

The hardened run is retained at `tmp/cgas-planner-blocker-investigation-20260730t103100/`. Its `probe.json` is byte-identical to the prior retained `20260730t102100` record; only the separate timing sidecar differs. The hardened test coverage rejects source traversal and symlinked source parents, output symlink/traversal paths, parent replacement after descriptor acquisition, and an active caller-owned SIGALRM timer. It also confirms restoration of an inactive caller-owned SIGALRM handler.

## Verification Commands

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_planner_blocker_probe.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_planner_blocker_probe.py scripts/phase3/cgas_planner_blocker_probe_fs.py tests/phase3/test_cgas_planner_blocker_probe.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_planner_blocker_probe.py scripts/phase3/cgas_planner_blocker_probe_fs.py tests/phase3/test_cgas_planner_blocker_probe.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_planner_blocker_probe --output tmp/cgas-planner-blocker-investigation-20260730t103300/probe.json
source ~/cd_vlaplan && git diff --check
```
