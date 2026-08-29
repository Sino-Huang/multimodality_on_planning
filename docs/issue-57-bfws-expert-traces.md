# Issue 57 BFWS expert traces

Issue 57 generated the complete exact `full_bfws_goal_count` development trace
release authorized by issue 56. The release contains 105 replay-verified
`search_episode_evidence_v4` episodes: 70 train and 35 dev instances across all
35 frozen domain-by-difficulty strata. It retains 69,019 exact teacher decisions
under each row's matching exact-reference expansion budget. The 45 frozen
held-out test tasks were not accessed.

The release manifest is
`data/bfws_phase_v1/exact-traces/manifests/bfws-expert-traces.json`. Each item
binds the source PDDL, semantic task identity, split, exact counters, canonical
tie-breaking, governed phase receipt, authoritative episode evidence, and the
derived bounded search-trace view. Both trace artifacts use deterministic gzip;
the derived JSON is compared after decompression with bytes reconstructed from
semantic evidence replay.

The release audit is
`data/bfws_phase_v1/exact-traces/manifests/bfws-trace-audit.json`. It rebuilds
the shared bounded BFWS model input from independent live and replay Search
Memory paths at all 69,019 positions, strict-parses and applies every teacher
operation, and measures input and target lengths with the exact pinned Qwen
tokenizer revision. Its six frozen teacher snapshots cover easy, medium, hard,
and equal-count low/middle/high input-token bins in
`data/bfws_phase_v1/exact-traces/manifests/bfws-teacher-snapshots.jsonl`. All
five audit rejection/mismatch counters are zero; observed maxima are 7,360 of
7,808 input tokens and 96 of 384 target tokens.

## Operator commands

Activate the confirmed environment and inspect the authorized run without
writing files:

```bash
source ~/cd_vlaplan
python scripts/generate_bfws_expert_traces.py --dry-run
```

Generate a new release:

```bash
source ~/cd_vlaplan
python scripts/generate_bfws_expert_traces.py
```

If the command is interrupted, resume it. Completed evidence is semantically
replayed and only missing tasks are generated. The CLI chooses a new governed
resume attempt ID when one is not supplied.

```bash
source ~/cd_vlaplan
python scripts/generate_bfws_expert_traces.py --resume
```

Every generation/resume task and per-trace audit prints `completed/total`,
elapsed time, and a decision-weighted ETA. Storage tasks may also print Plado's
known `Multiple types with name area` parser warning; their evidence must still
pass exact replay. Audit parts are written atomically, so an interrupted audit
can resume without repeating completed traces.

Replay-check the completed release without changing it:

```bash
source ~/cd_vlaplan
python scripts/generate_bfws_expert_traces.py --check
```

The retained governed completion receipt is
`data/bfws_phase_v1/execution-receipts/generation-run-issue-56-bfws-development-v1-issue-57-bfws-exact-traces-v1-resume-010.json`.
It records scientific-completion `PASS`, 105 replay-verified traces, and 69,019
audited exact decisions. Interrupted attempt reservations and invalid receipts
are intentionally not part of the release.
