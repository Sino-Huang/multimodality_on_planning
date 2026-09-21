# Issue #127 closeout (prospective training-seed replication)

#127 required: (1) a scope-frozen amendment committed before any launch; (2) replication
of 1-2 decision-relevant training cells with two additional prospective training seeds
(29, 71) frozen before launch; (3) the same frozen evaluation contracts and independent
replay of every episode as the original cells; (4) a synthesis seed-variance addendum
reporting every seed individually and aggregated; (5) no outcome-based cell swapping, no
modification of published verdicts, and the 336 GPU-h program cap unchanged. All of it
executed and verified; the ticket is closed as delivered.

## Delivered

- Amendment: `docs/experiments/expanded-study/seed-replication-amendment.md` +
  `configs/experiments/expanded-study/seed-replication-protocol.json` (committed 2026-09-20T13:07Z
  before any seed-29/71 artifact existed; explicit GPU authorization granted 2026-09-20
  after the frozen amendment was presented — design gate honoured).
- Cell A (headline cell, chosen by decision relevance): `best_first_add_greedy x
  multimodal-state` process-SFT on `expanded-panel-v2-qualified`; fresh LoRA adapter per
  seed on the frozen 512-record membership; the original cell's frozen evaluation
  contract (evaluation seed 17, greedy decoding, 2x reference decision call limit);
  comparators reused from the replay-verified baseline episodes.
- Cell set B (DAgger iteration-1 vs exposure-matched continued-SFT): `bfs x 3
  modalities x 2 arms` at iteration 1 from the verified seed-17 starting adapters on the
  verified seed-17 memberships (new seed perturbs only dropout RNG); evaluated on the
  original frozen panels; the seed-17 iteration-1 checkpoints evaluated inference-only
  under the same contract (the original program evaluated iteration-2 finals only).
- Synthesis addendum: `docs/experiments/expanded-study/synthesis-v1/seed-variance-addendum.md`
  (+ `seed-variance.json`, `seed-variance.csv`), canonical evidence
  `outputs/expanded-study/v1/seed-replication/evidence.json`, analysis
  `analysis.json`, protocol `preparation.json`.
- Independent replay: every new episode (534 = 48 baseline + 486 DAgger) replayed under
  the episode-verify hook; every comparator episode (486) replayed; checkpoint digests
  verified. Chain `outputs/expanded-study/v1/seed-replication-chain/complete.json`
  records every stage audit passing.

## Results

- Cell A successes per seed: 21/24 (seed 17), 21/24 (29), 22/24 (71) — mean 0.889,
  range [0.875, 0.917]. Headline contrast `process_sft - pretrained_base`: +0.875
  [+0.708, +1.000] / +0.875 [+0.750, +1.000] / +0.917 [+0.792, +1.000]; wins 21-0-3 /
  21-0-3 / 22-0-2. No sign flip; the primary positive contrast is training-seed robust
  in this cell.
- Cell set B: both arms score 0/72 unseen successes at every seed (consistent with the
  published iteration-2 trajectory, which also scores 0-1/24 per modality); the paired
  iteration-1 contrast is +0.000 [+0.000, +0.000] at every seed. Unseen invalid rates
  0.268/0.332/0.320 (dagger) vs 0.278/0.326/0.338 (continued_sft) — no seed-dependent
  divergence.

## Budget

- Committed by #127: expanded_baseline +3.4649 GPU-h (branch 9.9938 / 56 cap),
  dagger +9.3215 GPU-h (branch 20.2307 / 48 cap); total 12.7863 GPU-h, within the
  amendment's 6-15 GPU-h estimate. No new transfer was required; branch remainders
  sufficed. Program total 68.5244 / 336 GPU-h — cap unchanged; the ledger's only
  transfer remains the pre-existing #123 recovery-reserve transfer.
- Synthesis status: `not_modified` — all `synthesis-v1` published files byte-identical
  to their last published commit (git-clean); the synthesis `--check` ledger-attempt
  anchor (135) trips by design on any post-synthesis scheduler activity (pre-existing
  since #123/#124/#126); the published files themselves are unchanged.

## Disposition

#127 closes on this evidence. Execution repairs recorded in the ledger: one comparator
audit hook re-run after the `original_process_sft` -> `bfs-process_sft` filename mapping
fix (documented in `hook-result.json` rerun notes); one finalize resume (attempt 1 ran
prematurely against missing later-stage episodes and failed before producing output).
Neither alters any episode, checkpoint, or verdict.
