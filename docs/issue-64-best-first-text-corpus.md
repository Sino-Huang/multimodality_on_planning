# Issue 64 paired additive best-first text corpus

Issue #64 consumes only the completed issue-63 v3 release and materializes the
paired `best_first_add_w3` and `best_first_add_greedy` text-state corpora. The
source contains 75 semantic tasks, 150 traces, and 289,902 atomic successor
decisions: 200,895 train and 89,007 dev decisions.

## Successor contract

The original v1 contract produced a governed `VALID_STOP`: its lossless input
was 13,998 tokens on a hard VisitAll decision, above the pinned 7,808-token
input limit. Its contract and receipt are retained as immutable development
evidence; its partial output is excluded and is not scientific completion.

V2 compacted the inputs successfully, but its full panel still contained an
episode with 49,294 sequential decisions. Under the downstream 2x call budget,
one evaluation episode could therefore require 98,588 VLM calls. V2 was stopped
after its first materialization pass, before publishing scientific completion.

The active successor design is
`configs/experiments/best-first-paired-corpus-design-v3.json`; its authority is
`configs/experiments/best-first-paired-corpus-authorization-v3.json`. The
contract is `issue-64-best-first-paired-corpus-v3`, binds the v2 `VALID_STOP`,
and authorizes one `corpus_release` pass.

The process input losslessly factors canonical facts and repeated record
keys into simple JSON tables, with local argument tables for fact collections.
The first hard VisitAll input measures 4,980 tokens with the pinned tokenizer,
down from 11,811 for the v1 representation. Facts round-trip exactly to the
canonical source facts, and the representation remains directly flattenable as
text. A replay of all 10,044 expansions and 38,011 decisions in the exact hard
VisitAll trace that stopped v1 found 7,102 tokens at most among its 100 largest
serialized v2 prompts, leaving 706 tokens below the frozen input ceiling before
the tokenizer ceiling.

V3 admits a whole matched pair only when both algorithms require at most 1,024
reference decisions. This retains 64 pairs, 128 traces, all 12 domains, 24 of
26 domain/difficulty strata, and 31,531 process records. Eleven pairs and
258,371 records are excluded with `VALID_STOP` dispositions. The downstream 2x
evaluation rule can therefore allow at most 2,048 VLM calls per episode; actual
throughput qualification remains mandatory before #65 or #66 launches.

At each atomic successor decision, materialization reconstructs the compact
teacher and live inputs with the shared v2 builder, strict parses and applies
the teacher target through the Trusted Search Runtime, and checks the
operational state transition. Training messages reuse the exact live
system/user serializer and append the canonical teacher target.

The release contains:

- process, operational, and process-training gzip shards per task/algorithm;
- staged, seed-64 shuffled, and difficulty/algorithm round-robin mixed-order
  curriculum indexes for both views;
- one semantic-task split assignment per matched pair, stored once in the split
  ledger and referenced from rows by existing pair ID;
- zero-error semantic overlap, canonical input/input-target overlap,
  conflicting-target, future-leakage, live/training parity, target/runtime,
  state/action, and tokenizer audits;
- an exclusion ledger, release manifest, and pinned Qwen3-VL tokenizer
  contract.

V3 has no integrity mechanism. It does not create or consume hashes, checksums,
artifact-size identities, file comparisons, or regeneration comparisons. The
historical source traces and receipts remain untouched, but their legacy
integrity fields are ignored. V3 checks only scientific properties: PDDL replay,
strict typed-operation application, state/action semantics, split isolation,
coverage, leakage, and tokenizer/resource limits.

## Operator commands

The no-write checks are:

```bash
source ~/cd_vlaplan
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
python scripts/materialize_best_first_paired_corpus.py --dry-run
python scripts/materialize_best_first_paired_corpus.py --fixture-dry-run
```

Materialization prints per-trace progress, elapsed time, and ETA. It makes one
semantically audited pass and then publishes the governed outcome:

```bash
python scripts/materialize_best_first_paired_corpus.py --materialize
```

There is no integrity-check or resume mode. An interrupted attempt remains
non-scientific and requires a new governed attempt and output path.
