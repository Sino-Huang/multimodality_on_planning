# Issue 64 paired additive best-first text corpus

Issue #64 consumes only the completed issue-63 v3 release and materializes the
paired `best_first_add_w3` and `best_first_add_greedy` text-state corpora. The
source contains 75 semantic tasks, 150 traces, and 289,902 atomic successor
decisions: 200,895 train and 89,007 dev decisions.

## Frozen contract

The corpus design is
`configs/experiments/best-first-paired-corpus-design-v1.json`; its authority is
`configs/experiments/best-first-paired-corpus-authorization-v1.json`. The
contract is `issue-64-best-first-paired-corpus-v1` and authorizes only
`corpus_release` after the exact issue-63 generation receipt reports `PASS` and
scientific completion.

The corpus retains the issue-63 compact trace representation. At each atomic
successor decision, materialization reconstructs the live input with the shared
best-first model-input builder, verifies the inherited input commitment, strict
parses and applies the teacher target through the Trusted Search Runtime, and
checks the operational state transition. Training messages reuse the exact
live system/user serializer and append the canonical teacher target.

The release contains:

- process, operational, and process-training gzip shards per task/algorithm;
- staged, seed-64 shuffled, and difficulty/algorithm round-robin mixed-order
  curriculum indexes for both views;
- one semantic-task split assignment per matched pair;
- zero-error semantic overlap, canonical input/input-target overlap,
  conflicting-target, future-leakage, live/training parity, target/runtime,
  state/action, and tokenizer audits;
- a deterministic release manifest and pinned Qwen3-VL tokenizer contract.

No new SHA-256 integrity records are introduced. Source authority is checked
structurally and semantically, task artifacts are compared byte-for-byte,
cross-split audits compare canonical bytes directly, and release checking
regenerates the complete tree and compares bytes directly. The inherited #63
per-decision input commitment remains necessary to validate reconstructed input
bytes without storing every full input in the compact source trace.

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
