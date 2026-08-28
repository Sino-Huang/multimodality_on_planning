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

Every generation/resume task prints a start line and a completion line with
`completed/total`, elapsed time, and a decision-weighted ETA. Storage tasks may
also print Plado's known `Multiple types with name area` parser warning; their
evidence must still pass exact replay.

Replay-check the completed release without changing it:

```bash
source ~/cd_vlaplan
python scripts/generate_bfws_expert_traces.py --check
```

The retained governed completion receipt is
`data/bfws_phase_v1/execution-receipts/generation-run-issue-56-bfws-development-v1-issue-57-bfws-exact-traces-v1-resume-001.json`.
It records `PASS`, 105 replay-verified traces, and 69,019 exact decisions. The
initial interrupted attempt's reservation is intentionally not part of the
release.
