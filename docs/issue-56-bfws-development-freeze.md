# Issue 56 BFWS development freeze

Issue 56 authorizes the development phase `issue-56-bfws-development-v1` for
the complete unpruned `full_bfws_goal_count` arm selected by issue 55. It does
not generate expert traces, materialize a corpus, train a model, or access an
efficacy test split. Those runs belong to issues 57–59 and must present this
phase receipt before creating output.

## Frozen data

The issue-55 qualification contains 3,186 replay-proven solutions: 2,905 from
the source train split and 281 from the former test split. The former-test rows
are excluded from this development phase because that split was inspected
during algorithm selection.

The frozen development panel contains 105 nontrivial source-train instances in
35 domain-by-source-difficulty strata. Within every retained stratum, the first
three semantically distinct tasks under the recorded deterministic ordering are
assigned two to train and one to dev. The panel contains 69,019 exact BFWS
decisions and 25,573 exact expansions.

The replacement held-out test manifest contains 45 semantic-unique source-dev
instances, one in every domain-by-difficulty cell. Issue 55 never ran BFWS on
those instances, and neither exact-search outcome nor model outcome influenced
their selection. This development authorization forbids reading them in traces,
corpus construction, training, references, or the development structural gate;
a successor authorization is required before efficacy testing.

## Frozen contracts

The phase index binds separate trace, corpus, training, reference, threshold,
and stop manifests under `configs/experiments/` plus one authorization manifest.
Important inherited corrections from the BFS v6–v8 work are:

- exact bounded Search Memory exposes task context and every BFWS candidate's
  duplicate, novelty, priority, insertion, and enqueue facts;
- corpus and live evaluation use the same bounded input builder;
- only the oldest of 16 accepted deltas may be removed, while required task and
  candidate facts may never be truncated;
- corpus release must prove strict target applicability, zero semantic/input
  leakage, token-budget coverage, and byte-identical regeneration;
- five seeds are trained, but only the final checkpoint is rolled out;
- each model episode receives twice its matching exact-reference decision count;
- model rollout requires outcome-blind hardware qualification, float32
  inference, deterministic batching, scalar/batch and repeated-batch probes,
  complete selected coverage, and one 20-hour gate clock.

The required corpus audits are frozen acceptance values, not claimed results.
Issue 58 must measure them before corpus release.

## Operator checks

Both commands print stage-by-stage progress directly in the terminal. The dry
run writes nothing; the check independently regenerates every frozen byte from
the retained local issue-55 qualification output.

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
source ~/cd_vlaplan

python scripts/create_bfws_phase_v1_manifests.py --dry-run
python scripts/create_bfws_phase_v1_manifests.py --check
```

There is no long-running issue-56 experiment command. Issues 57 and 58 must add
resumable, progress-and-ETA-visible runners before the human operator starts
their actual trace or corpus materialization runs.
