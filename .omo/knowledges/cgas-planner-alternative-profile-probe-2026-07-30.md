# CGAS Planner Alternative Profile Probe

- CLI: `python -m scripts.phase3.cgas_planner_alternative_profile_probe --output tmp/cgas-planner-alternative-profile-<token>/probe.json`.
- It is diagnostic-only and non-authoritative. It freezes and verifies the bundle, characterization member, and draft hashes before and after planner execution.
- The output executes BFS caps 30000/100000 and IW widths 2/3 with a 10000 novelty cap, disabled recovery, zero retained trace steps, and two sequential repetitions per representative/profile.
- Canonical outcomes are in `probe.json`; runtime measurements are isolated in `timings.jsonl` so deterministic evidence does not include timing variance.
- `open_probe_output` permits only blocker or alternative namespaces and publishes via a descriptor-bound, write-once directory after inode-pinning `tmp`.
- Final retained evidence is `tmp/cgas-planner-alternative-profile-final-20260730t120000/probe.json`, SHA-256 `cc95e968cdb316d3040e0b6a15896615751da2298e2e5528cab566faa01c9d58`. Its root `probe_implementation_sha256` is `b95e52797d049617f901fdd99254ea7add935ae3187053fe9adfedbb179459c5`, binding the exact current source bytes; every profile serializes the complete effective limits map and frozen bundle, characterization, and draft hashes matched before/after.
- The older `tmp/cgas-planner-alternative-profile-manual-20260730t104500/probe.json`, SHA-256 `b1b127262fbf2696db2207df852925d38fc1630710474c725168282f3cd16878`, is retained as outcome-only evidence and superseded as incomplete-contract evidence.
- Results: BFS 30k reached 30001 and BFS 100k reached 100001 expansions for all representatives, both resource-limited with no plan. IW(2) exhausted without a plan at dev/test/train counts 8188/8019/8725. IW(3) reached 10001 for all representatives, resource-limited with no plan. Replays did not satisfy goals; recovery was absent and repeated runs matched.
- Scoped conclusion: no tested profile merits a 93-row sweep or authoritative successor characterization. This does not establish task unsolvability or universal planner failure. Broader algorithm or trace-design changes require separate owner approval.
