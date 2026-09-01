# Issue 63 paired A* expert traces

Issue 63 materializes one exact `astar_hmax` and one exact
`astar_landmark_count` episode for every issue-62 pair. Both halves use the same
frozen source-row expansion ceiling and the existing Trusted Search Runtime,
`search_episode_evidence_v4`, and derived `astar_trace_view_v1`. No alternate
runtime or trace schema is introduced.

The generator fully loads and validates the committed issue-62 freeze and its
authorization peer before it creates an output directory or governed receipt.
One phase-gate bridge revalidates those persisted peers, requires exact equality
of the freeze, authorization metadata, canonical phase receipt, and all six
component products, requires the PASS `trace_generation` phase receipt, and
checks the exact runtime contract binding. Only then does it issue generic
attempt-bound **operational execution receipts** for the selected attempt and
output. Those operational receipts are not the issue-62 scientific authority;
they consume it after attempt selection. File existence or a self-authored PASS
payload cannot authorize execution. The persisted phase receipt remains bound
in every request/evidence pair and release output. Missing, malformed,
wrong-stage, wrong-contract, mismatched, or non-PASS ancestors stop the run.
Expansion-budget termination after a valid start is a governed
`VALID_STOP` resource exhaustion and publishes neither pair half. Frontier
exhaustion on a replay-proven solved source, malformed provenance, invariant or
replay failure, cap disagreement, and pair mismatch are `INVALID`. A release
manifest is published only after complete pair coverage and a zero-error
independent release audit.

Both adapter halves and alignment are first written beneath the pair's
non-authoritative `.staging` directory, replayed and audited there, marked with
the complete pair metadata, and atomically renamed as one directory under
`pairs/<pair-id>`. Resume may discard non-authoritative scratch staging only
when it contains no retained pair evidence; retained staging evidence causes a
fail-safe stop. An
incomplete crash-created final pair is atomically moved byte-for-byte to its
deterministic `.quarantine/<pair-id>` location before regeneration. An existing
quarantine causes a fail-safe stop rather than overwrite or deletion. A complete
retained pair is accepted only after exact hashes and replay; different complete
bytes are immutable. Audit parts use atomic writes. The final manifest is itself
atomic and follows only complete coverage.

Each pair manifest binds the task and both gzip artifacts by path, SHA-256, and
byte size, plus pair identity, phase receipt, adapter-specific exact counts and
results, and the canonical `(f, generation_serial)` tie break. Alignment is by
world-state source: a source aligns only when it occurs exactly once in each
trace, and then grounded action and target world state must agree. Repeated and
adapter-exclusive sources remain explicitly unmatched; different heuristic
values, paths, progression, and counts are allowed.

Every audited teacher target has exactly `canonical_rationale`,
`typed_operation`, and `runtime_result: null`. Independent replay proves that
the operation is an exact runtime-applicable successor. Required task/current,
candidate target state/node, best-cost, closed/frontier/dominated/pruned, and
landmark progression fields are retained. The audit does not require or invent
full frontier or best-g tables. Real audits use the pinned Qwen revision and
7808/384 input/output limits; fixture validation uses a deterministic lightweight
counter and makes no tokenizer claim. The stable rationale is derived in this
issue-63 projection layer; it is not a new mandatory field in
`search_episode_evidence_v4`, so previously valid A* v4 artifacts remain valid.
Each deterministic snapshot contains the complete bounded model input and
canonical teacher target as well as identifiers and measured token counts.

## Operator commands

The fixture-only command executes and audits both adapters on committed fixtures
inside temporary storage. It writes no repository or requested output artifacts:

```bash
source ~/cd_vlaplan
cd /scratch/punim0478/sukaih/multimodality_on_planning_issue60
python scripts/generate_astar_paired_expert_traces.py --fixture-dry-run
```

Future real commands, after issue-62 products are committed, are:

```bash
source ~/cd_vlaplan
cd /scratch/punim0478/sukaih/multimodality_on_planning_issue60
python scripts/generate_astar_paired_expert_traces.py --dry-run
python scripts/generate_astar_paired_expert_traces.py --attempt-id issue-63-attempt-001
python scripts/generate_astar_paired_expert_traces.py --attempt-id issue-63-attempt-002 --resume
python scripts/generate_astar_paired_expert_traces.py --check
```

There is intentionally no CLI budget override. Progress is flushed canonical
JSON and identifies stage, pair, completed/total work, elapsed time, and ETA.
The command emits `ancestor_preflight` start/completion records around the
persisted issue-62 validation before pair-level progress begins, so the initial
authority check never appears stalled. A missing issue-62 authority makes real
`--dry-run` exit nonzero with `status: ancestor_authorization_absent` and write
nothing.
