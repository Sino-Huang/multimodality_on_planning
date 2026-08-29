# Issue 58 BFWS text corpus release

Issue #58 releases the authorized text-state corpus for the complete unpruned
`full_bfws_goal_count` arm. It consumes only the 105 replay-verified development
traces released by #57. It does not read or authorize the fresh 45-task test
manifest, and it runs no learning command.

## Operator commands

Activate the confirmed environment and inspect the frozen work before writing
artifacts:

```bash
source ~/cd_vlaplan
python scripts/materialize_bfws_text_corpus.py --dry-run
```

Materialize the release. The command prints trace and decision progress,
elapsed time, and ETA directly in the terminal. If interrupted, give the
resumed governed attempt a fresh ID:

```bash
python scripts/materialize_bfws_text_corpus.py \
  --resume \
  --attempt-id issue-58-bfws-text-corpus-v1-resume-004
```

Independently regenerate every corpus shard, curriculum, split ledger, and
training projection into a temporary root and require byte equality:

```bash
python scripts/materialize_bfws_text_corpus.py --check
```

## Retained release

The release is rooted at `data/bfws_phase_v1/corpus-release/` and contains:

- 69,019 atomic process records and matching ms-swift message projections;
- 67,215 accepted-transition operational records;
- staged process and operational curricula spanning all 35 structural strata;
- 105 immutable semantic-task split assignments (70 train, 35 dev);
- explicit row-to-episode-position evidence bindings;
- a corpus audit and release manifest.

The process projection has 47,780 train and 21,239 dev examples. It uses the
shared `bounded_bfws_search_memory_v1` builder and canonical BFWS chat
serializer, 16 accepted deltas, a 7,808-token input limit, and a 384-token
output limit. Observed maxima are 7,360 input tokens and 96 target tokens.

The retained audit reports zero semantic, canonical-input, and input-target
overlap across splits; zero identical inputs with conflicting targets; zero
future-step leakage; zero live/corpus mismatch; zero parse, runtime-teacher, or
token-budget rejection; and zero held-out instances. The independent full-tree
regeneration check passed byte-identically.

The final governed PASS receipt is
`data/bfws_phase_v1/execution-receipts/generation-run-issue-56-bfws-development-v1-issue-58-bfws-text-corpus-v1-resume-004.json`.
It records `byte_identical_regeneration: true`; scientific PASS is emitted only
after that independent full-tree comparison completes.
