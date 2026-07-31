# Phase 3 CGAS Planner Alternative Profile Probe

## Scope

Added a non-authoritative diagnostic CLI for the three frozen hard representatives. It runs four alternative profiles twice, sequentially, and writes canonical scientific outcomes separately from per-invocation timing records.

Profiles:

- `bfs_30000`: BFS with `max_expansions=30000` and `max_trace_steps=0`.
- `bfs_100000`: BFS with `max_expansions=100000` and `max_trace_steps=0`.
- `iw_2`: IW width/max-width `2`, novelty cap `10000`, recovery disabled, and `max_trace_steps=0`.
- `iw_3`: IW width/max-width `3`, novelty cap `10000`, recovery disabled, and `max_trace_steps=0`.

All other characterization limits are preserved and serialized into each profile record. The probe verifies frozen authoritative bundle, characterization, and draft hashes before and after execution. It does not change authoritative artifacts or current-profile evidence.

## Output Contract

The CLI accepts only a unique write-once target matching:

```text
tmp/cgas-planner-alternative-profile-<token>/probe.json
```

It writes `probe.json` and `timings.jsonl` through the opened directory descriptor. The shared filesystem helper permits only the blocker and alternative diagnostic namespaces and inode-pins `tmp` between validation and open.

## Run

```bash
RUN_ID="manual-$(date -u +%Y%m%dt%H%M%S)-$$"
source ~/cd_vlaplan && python -m scripts.phase3.cgas_planner_alternative_profile_probe --output "tmp/cgas-planner-alternative-profile-${RUN_ID}/probe.json"
```

Expected signal: exit code 0, one canonical `probe.json`, and 24 JSONL timing records, one for each profile/representative/repetition invocation.

## Retained Evidence And Scope

Final retained probe: `tmp/cgas-planner-alternative-profile-final-20260730t120000/probe.json` with SHA-256 `cc95e968cdb316d3040e0b6a15896615751da2298e2e5528cab566faa01c9d58`. It binds the exact current probe source bytes with `probe_implementation_sha256` `b95e52797d049617f901fdd99254ea7add935ae3187053fe9adfedbb179459c5` and serializes the complete effective limits map for every profile.

The earlier `tmp/cgas-planner-alternative-profile-manual-20260730t104500/probe.json` record, SHA-256 `b1b127262fbf2696db2207df852925d38fc1630710474c725168282f3cd16878`, remains retained as outcome-only evidence but is superseded because it lacks the complete implementation-contract binding.

- BFS 30k: all representatives reached `30001` expansions, `skipped_resource_limit`, and no plan.
- BFS 100k: all representatives reached `100001` expansions, `skipped_resource_limit`, and no plan.
- IW(2): dev/test/train reached `8188`/`8019`/`8725` expansions, `failed_no_plan_extracted`, and no plan.
- IW(3): all representatives reached `10001` expansions, `skipped_resource_limit`, and no plan.
- Every replay left the goal unsatisfied; recovery was absent and repeated runs matched.

Scoped conclusion: none of these tested profiles merits a 93-row sweep or authoritative successor characterization. This is not a task-unsolvability claim or a universal planner-failure claim. Broader algorithm or trace-design work requires separate owner approval.

## Verification

```bash
source ~/cd_vlaplan && pytest tests/phase3/test_cgas_planner_alternative_profile_probe.py tests/phase3/test_cgas_planner_blocker_probe.py -q
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_planner_alternative_profile_probe.py scripts/phase3/cgas_planner_blocker_probe_fs.py tests/phase3/test_cgas_planner_alternative_profile_probe.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_planner_alternative_profile_probe.py scripts/phase3/cgas_planner_blocker_probe_fs.py tests/phase3/test_cgas_planner_alternative_profile_probe.py
git diff --check
```

Observed results: `15 passed` for both probe suites, basedpyright `0 errors`, compileall success, and `git diff --check` success. The final run retained identical before/after authoritative hashes and recorded all 24 timing records below 120 seconds.
