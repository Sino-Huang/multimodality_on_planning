# Qualified expanded panel (#117)

Goal 2 has prepared and frozen **24 new tasks across twelve domains**, with two
structural strata per domain. The final binding is
[`final-panel.json`](../../../configs/experiments/expanded-study/final-panel.json).
Hardware and input qualification passed. Cost admission is explicitly conditional
on historical workload behaviour; maximum-allowance completion is not guaranteed.

## Scope and selection

The twelve domains are 15puzzle, blocksworld, depot, driverlog, elevators, ferry,
grid, gripper, logistics, storage, towers_of_hanoi and visitall. This carries
forward #62/#64's paired-heuristic scope, excluding Freecell, Snake and Sokoban;
the later fifteen-domain modality corpus also contains BFS/BFWS-only sources.
The recovered decision and source manifest are in `panel-domain-scope.json`.

Structural profiles and seed ranges were fixed before candidate screening.
All 384 candidate dispositions are retained. Whole-task comparison covers 4,970
historical contexts, including prior matched-study candidates, and rejects object
renamings as new instances. The independent audit also checks within-panel
separation and source-goal/walk provenance. Only new-task assets were generated;
old corpora, scenes, ledgers and all twelve v5 adapters remain intact.

V1 rejected Storage using the historical Cartesian grounding estimate. The
prospective v2 correction uses the current additive runtime's actual type-pruned
operator count, retaining all profiles, seeds, source tasks and ceilings. Both
Storage strata then passed; no domain or stratum was dropped. See
[the correction record](panel-grounding-correction.md).

## Evidence

- [Independent audit](panel-independent-audit.json): all 24 source/profile/split,
  object-renaming, goal and reference/view bindings. Source PDDL snapshots and
  generating walks are committed under `configs/experiments/expanded-study/tasks/`.
- [Reference views](panel-reference-views.json): 1,866 states and 4,310 decisions,
  separate complete source-goal/context pages, and unlabelled 128px scenes.
  Maximum observed reference inputs are 4,421 text, 5,908 visual and 7,659
  multimodal tokens. These observed maxima are not claimed as off-policy bounds.
- [Live views](panel-live-views.json): all tasks exercise a newly accepted state
  or verify closure of the reference catalog. `ExpandedTaskViews` renders only
  after the producing operation, preserves unlabelled rasterization, and replays
  saved parent paths when restoring its PDDL authority. Failed first-attempt
  evidence remains in the shared ledger.
- [Common memory](panel-common-memory.json): all 4,310 decisions retain identical
  common input across modalities, at most sixteen accepted deltas and at most
  5,189 observed common-input bytes. Standard-runtime token-counter replay passed.
- [GPU qualification](panel-gpu-qualification.json): both A100s passed twelve
  probes each, with four fixed v5 adapters loaded per modality. Probes cover
  32,384-token single inputs, 24,000-token padded batches, the largest page
  geometry, and full 384-token outputs. Ports were 18800 and 18801. Raw unscored
  probe outputs, timings, memory measurements and terminal hooks are retained.
- [Requirement audit](goal2-completion-audit.json) maps the deliverables to evidence.

The complete projected-input guard and model-policy guard reject oversized
requests without truncation. Static/goal page counts are fixed per task; every
new initial/current state uses the same 128px geometry. The reference catalog is
not full reachability closure: off-reference images are supplied on demand under
the tested accepted-operation boundary. Unlabelled scenes can lose identities;
semantic information equality with text is not claimed.

## Cost admission

The measured full-call/full-output allowance projection is **574.08 GPU-hours**,
which does not fit this branch's 56 hours. It remains reported as infeasible.

The separately declared [historical-consumption method](panel-cost-admission.md)
projects **35.01 GPU-hours**, plus **0.733 GPU-hours already spent** on shared
readiness and qualification. It scales actual v5 worker time by reference-work
complexity, current measured slowdown and a 1.25 margin. V5 had only three final
problems and many early invalid-operation stops, so this extrapolation is
conditional. It does not promise every maximum allowance can be consumed.

All 24 tasks and all 1,152 logical bindings remain fixed. Goal 3 must enforce the
original shared cap and report every missing binding if it is exhausted. No
additional allocation, easier replacement tasks or favourable retries are
introduced. The original calendar cutoffs remain unchanged.

## Commands and Goal 3 handoff

Read-only verification, from the repository root:

```bash
source ~/cd_vlaplan
python scripts/verify_expanded_panel.py
python scripts/run_expanded_study.py status
```

The finalizer has already run; it refuses to overwrite the existing freeze time.
Reproduction jobs and their completion hooks are under
`configs/experiments/expanded-study/`; successful job IDs intentionally refuse
duplicate launches. The retained local outputs are required for full verification.

Goal 3 consumes `final-panel.json`, loads task view records from its `view_report`,
and constructs `ExpandedTaskViews(root, task_record, attempt_output, endpoint)`.
Use the standard `VisualSession` token counter and unchanged family semantics,
the frozen 384-token output allowance, qualified single/batch limits, and the
shared scheduler. Each episode needs its own persistent live-view output directory.
Restore/replay uses `read_only=True`; it must never generate missing replay images.

The matrix is four algorithms × three modalities × 24 tasks × base/SFT/random/exact
= 1,152 logical bindings, including 576 model episodes. Retain all logical control
bindings even if physical reference traces are shared under identical contracts.
Random-valid is oracle-assisted. Use only the fixed v5 adapters and seed 17; no
retraining is authorized by this goal. Goal 3 owns its actual episode runner,
execution and independent result replay. This goal has run no expanded baseline
planning episode and makes no efficacy claim.
