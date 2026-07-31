# CGAS Planner Blocker Probe

- `scripts/phase3/cgas_planner_blocker_probe.py` is isolated from characterization, selection, and publication. It verifies the pinned bundle (`942d7be...daf4`), characterization member (`4596ffde...0417`), draft (`409f7127...4630d`), and run fingerprint (`0856e765...893a`) before and after work.
- The only accepted output shape is an absent `tmp/cgas-planner-blocker-investigation-<token>/probe.json`; canonical scientific JSON is byte-stable because timings are written separately to `timings.jsonl`.
- The three 12-object representatives replay their persisted `plan/sas_plan`. Under unchanged `CHARACTERIZATION_LIMITS`, canonical BFS reports 10001 resource-limited expansions; native recovery-disabled IW(1) fails after novelty exhaustion at dev 73, test 71, and train 90 expansions.
- Source inputs reject lexical traversal and symlinked parent components after canonical repository containment. Evidence creation opens the newly created owner-only directory with `O_NOFOLLOW`; both output files use that descriptor with no-follow/no-replace flags, so pathname parent replacement cannot redirect publication.
- The planner timeout is fresh-process-only. A nonzero `ITIMER_REAL` rejects the probe without replacing the caller timer or SIGALRM handler; a caller handler without an active timer is restored afterward.
- Hardened runtime evidence is `tmp/cgas-planner-blocker-investigation-20260730t103100/probe.json`, byte-identical to the pre-hardening normalized evidence at `20260730t102100`.
