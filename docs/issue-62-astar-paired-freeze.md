# Issue 62 paired A* development freeze

Issue 62 defines the preparatory phase
`issue-62-astar-paired-development-v1` for a paired comparison of
`astar_hmax` and `astar_landmark_count` on the same text-state tasks. The phase
is descended from issue 38. It validates contracts and may authorize only trace
generation and corpus release for downstream issues 63 and 64. It does not
authorize training, efficacy-test access, model rollout, or scientific
completion.

## Paired authority

Every source task is loaded through the shared `PDDLStateAuthority`. The task
component binds the raw task bytes, normalized domain and problem hashes, and
semantic-task identity. Both heuristic adapters must accept that same authority;
neither A* outcome may influence panel selection. A semantic task belongs wholly
to one split and every pair requires one independently replayed trace from each
adapter under the shared `AStarController`, which implements the Trusted Search
Runtime.

The freeze binds exactly six components: task, trace, corpus, model, budget, and
analysis. The trace contract fixes stable candidate ordering, `(f,
generation_serial)` priority, cheaper-path reopen behavior, and goal testing only
when the frontier head is popped. Decision and expansion accounting remains
adapter-specific. Corpus audits are required acceptance values rather than
claimed results. The model revision, seed policy, final-checkpoint-only rollout,
per-adapter budgets, outcome-blind panel selection, precision probes, paired
analysis, fixed bootstrap, and terminal outcomes are all frozen before any
downstream materialization.

## Source status and schemas

The real source manifest is expected at
`data/astar_paired_phase_v1/source-task-manifest.jsonl`. It is intentionally not
committed yet. Therefore this repository currently has no final paired panel and
no real issue-62 authorization products. Absence of that source is a blocking
precondition, not an invitation to substitute fixtures or claim scientific
authorization.

Each source JSONL line must be one canonical, finite JSON object with exactly
five non-empty string fields and a positive integer
`generation_max_expansions`, followed by one LF byte (`\n`). Duplicate
keys, blank lines, CRLF, a missing final LF, non-finite constants, whitespace,
and noncanonical key ordering are rejected before products are considered:

```json
{"difficulty":"easy","domain_id":"blocksworld","generation_max_expansions":16,"instance_id":"test-only-example","split":"train","task_path":"tests/fixtures/planning/blocksworld_nontrivial.json"}
```

`split` must be `train` or `dev`; `task_path` is relative to the source manifest
directory (the repository root for the default path) and names a JSON task with
`domain_pddl` and `problem_pddl`. Semantic identities and pair IDs must be unique
across the complete panel. The same semantic task cannot appear in either the
same or a different split.

A reviewed canonical source audit must also exist at
`data/astar_paired_phase_v1/source-audit.json`. An alternate location may be
passed with `--source-audit`. Its exact schema is:

```json
{
  "audit_id": "reviewed-source-audit-id",
  "efficacy_data": false,
  "expected_pair_count": 2,
  "expected_task_count": 2,
  "generation_budget": {
    "adapters": ["astar_hmax", "astar_landmark_count"],
    "decision_outcome_blind": true,
    "frozen_before_astar_execution": true,
    "max_expansions_by_difficulty": {"easy": 0, "hard": 0, "medium": 0},
    "policy": "shared_ceiling_by_development_difficulty",
    "task_specific_overrides_allowed": false
  },
  "panel_purpose": "paired_astar_development",
  "replay_proven": true,
  "review_status": "reviewed",
  "schema_version": "astar_paired_source_audit_v1",
  "selection_outcome_blind": true,
  "source_authorization": {
    "identifier": "issue-56-bfws-development-authorization-v1",
    "path": "configs/experiments/bfws_phase_authorization_v1.json",
    "schema_version": "bfws_phase_authorization_v1",
    "sha256": "<sha256-of-canonical-authorization>",
    "size_bytes": 0
  },
  "source_evidence": {
    "identifier": "issue-57-bfws-expert-traces-v1",
    "path": "data/bfws_phase_v1/exact-traces/manifests/bfws-expert-traces.json",
    "schema_version": "bfws_expert_trace_generation_v1",
    "sha256": "<sha256-of-canonical-evidence>",
    "size_bytes": 0
  }
}
```

Replace each placeholder hash and size with the exact canonical artifact values,
and replace each zero generation cap with a reviewed positive integer before any
real source is accepted. Human/real cap values remain intentionally absent.
The identifiers, paths, and schemas are allowlisted rather than free-form. The
authorization must be the issue-56 PASS development authority with efficacy
access false. The evidence must be the concrete replay-proven issue-57 BFWS
expert-trace manifest; every source row must match one evidence trace by domain,
difficulty, instance, split, and semantic-task identity. Both expected counts
must equal the source and evidence count. The task component and generated
authorization bind the source JSONL, audit, issue-56 authorization, and issue-57
evidence by artifact-root-relative path, SHA-256, and byte size. An arbitrary or
self-authored audit therefore cannot produce PASS.

The source audit freezes exactly the two adapters, outcome-blind decisions,
pre-execution freezing, one positive `easy`/`medium`/`hard` shared ceiling,
policy `shared_ceiling_by_development_difficulty`, and no task-specific
overrides. Every row's `generation_max_expansions` must equal its difficulty
ceiling. The budget component binds this object and
`expert_generation_expansion_limit: source_row.generation_max_expansions`.

The bounded observable contract is
`bounded_astar_search_memory_v1`, built by
`build_bounded_astar_model_input` and serialized by
`serialize_astar_message_prefix`. Teacher and live projections are canonical-byte
identical. Only oldest accepted deltas may be removed; static task, current,
candidate, pruning, best-cost, frontier, closed, and progression facts are never
removed or altered. Required-facts overflow is an error. Pinned-token overflow
and teacher/live byte parity remain required future audits for issues 63 and 64;
this phase adds no tokenizer dependency.

The budget additionally freezes float32 qualified accelerator inference, scalar,
batch, and repeated-batch qualification, all adapter cache-key ingredients, a
single non-restartable clock started only after hardware qualification, and
VALID_STOP on qualification failure. Full-panel-first and fallback selection are
both outcome-blind. Pairing, parity, replay, or provenance mismatch is INVALID;
ordinary threshold or resource failure is VALID_STOP; failed predecessor is
ANCESTOR_STOP; and only complete coverage can PASS. Training remains
unauthorized, with one distinct cell at seed 17 and pinned `accelerate 1.5.2`,
`peft 0.17.1`, `torch 2.7.1`, and `transformers 4.57.0` contracts. Corpus audit
zeros are required future acceptance results, not measured results.

The six exact, currently unauthorized process-SFT cells cross each of
`astar_hmax` and `astar_landmark_count` with `staged`, `shuffled`, and
`mixed_order`; every cell has only training seed 17. Nonfinal checkpoints are
teacher-forced diagnostics only and only a final checkpoint could roll out under
a successor authorization. Fallback panel cost is the sum of both adapters'
exact reference decision counts per pair; it selects one lowest-cost pair per
domain with deterministic tie-break `[summed_exact_decision_count, difficulty,
pair_id]` and no model outcomes. Analysis freezes a whole-problem paired
percentile bootstrap at confidence 0.95, 10,000 resamples, and seed 1729.

No efficacy effect threshold is invented or authorized by issue 62. A successor
authorization is required before any model efficacy run. The only deterministic
issue-63/64 acceptance values are pair completeness, replay, and parity rates of
1.0, plus mismatch, overflow, and rejection counts of zero. Pairing, parity,
replay, or provenance mismatch is INVALID; ordinary threshold or resource
failure is VALID_STOP; failed predecessor is ANCESTOR_STOP; PASS requires
complete selected coverage.

## Operator checks

The fixture command validates only the contract against committed planning
fixtures. It writes nothing and reports `contract_validation_only` with
`scientific_authorization: false`:

```bash
source ~/cd_vlaplan
cd /scratch/punim0478/sukaih/multimodality_on_planning_issue60
python scripts/create_astar_paired_phase_v1_manifests.py --fixture-contract --dry-run
```

After a reviewed real source manifest is supplied, dry-run the real inputs before
the actual refresh and check commands:

```bash
source ~/cd_vlaplan
cd /scratch/punim0478/sukaih/multimodality_on_planning_issue60
python scripts/create_astar_paired_phase_v1_manifests.py \
  --source-manifest data/astar_paired_phase_v1/source-task-manifest.jsonl \
  --source-audit data/astar_paired_phase_v1/source-audit.json \
  --dry-run
python scripts/create_astar_paired_phase_v1_manifests.py \
  --source-manifest data/astar_paired_phase_v1/source-task-manifest.jsonl \
  --source-audit data/astar_paired_phase_v1/source-audit.json \
  --refresh
python scripts/create_astar_paired_phase_v1_manifests.py \
  --source-manifest data/astar_paired_phase_v1/source-task-manifest.jsonl \
  --source-audit data/astar_paired_phase_v1/source-audit.json \
  --check
```

Every validation loop prints flushed JSON terminal progress containing
`completed`, `total`, `elapsed_seconds`, and `estimated_remaining_seconds`.
`--refresh` creates missing deterministic manifests only after all real source
rows pass. Existing byte-identical products are accepted, but a differing v1
product is immutable and rejected: changed source or contracts require v2.
`--check` independently requires byte-identical regeneration. Operators must not
redirect those progress records away from the terminal or launch training or an
efficacy experiment from this issue.
