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

The active successor design is
`configs/experiments/best-first-paired-corpus-design-v2.json`; its authority is
`configs/experiments/best-first-paired-corpus-authorization-v2.json`. The
contract is `issue-64-best-first-paired-corpus-v2`, binds the v1 `VALID_STOP`,
and authorizes only `corpus_release` after the exact issue-63 generation receipt
reports `PASS` and scientific completion.

The v2 process input losslessly factors canonical facts and repeated record
keys into simple JSON tables, with local argument tables for fact collections.
The first hard VisitAll input measures 4,980 tokens with the pinned tokenizer,
down from 11,811 for the v1 representation. Facts round-trip exactly to the
canonical source facts, and the representation remains directly flattenable as
text. A replay of all 10,044 expansions and 38,011 decisions in the exact hard
VisitAll trace that stopped v1 found 7,102 tokens at most among its 100 largest
serialized v2 prompts, leaving 706 tokens below the frozen input ceiling before
full-release audit.

At each atomic successor decision, materialization reconstructs the compact
teacher and live inputs with the shared v2 builder, strict parses and applies
the teacher target through the Trusted Search Runtime, and checks the
operational state transition. Training messages reuse the exact live
system/user serializer and append the canonical teacher target.

The release contains:

- process, operational, and process-training gzip shards per task/algorithm;
- staged, seed-64 shuffled, and difficulty/algorithm round-robin mixed-order
  curriculum indexes for both views;
- one semantic-task split assignment per matched pair;
- zero-error semantic overlap, canonical input/input-target overlap,
  conflicting-target, future-leakage, live/training parity, target/runtime,
  state/action, and tokenizer audits;
- a deterministic release manifest and pinned Qwen3-VL tokenizer contract.

V2 neither creates nor consumes hash-integrity evidence. Source authority is
checked structurally and semantically, task artifacts are compared
byte-for-byte, cross-split audits compare canonical bytes directly, and release
checking regenerates the complete tree and compares bytes directly. The
inherited `input_sha256` fields remain untouched in the frozen #63 source traces
but are not part of v2 validation. The legacy v1 replay path remains available
only to reproduce its already-retained stop.

## Operator commands

The no-write checks are:

```bash
source ~/cd_vlaplan
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
python scripts/materialize_best_first_paired_corpus.py --dry-run
python scripts/materialize_best_first_paired_corpus.py --fixture-dry-run
```

Materialization prints per-trace progress, elapsed time, and ETA. It publishes a
scientific `PASS` receipt only after an internal byte-identical full-tree
regeneration succeeds:

```bash
python scripts/materialize_best_first_paired_corpus.py --materialize
```

If interrupted before a receipt is published, resume deterministic shards with:

```bash
python scripts/materialize_best_first_paired_corpus.py --materialize --resume
```

After a `PASS`, independently repeat complete regeneration without writes:

```bash
python scripts/materialize_best_first_paired_corpus.py --check
```
