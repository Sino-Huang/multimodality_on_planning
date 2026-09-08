# Stored 128 × 128 scene assets

The supervisor selected **128 × 128 PNGs on disk**, with larger VLM inputs
permitted at use time. There is no total-byte cap. `scenes128.json` is a scoped
successor authorization for scene assets, not an authorization to bypass the
remaining partial-goal/model-input gates.

## Commands

In terminal 1, start four isolated localhost backend processes:

```bash
source ~/cd_vlaplan
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
.cache/issue70-backend-venv/bin/python scripts/serve_issue70_planimation.py --workers 4
```

This uses ports 18092–18095, one per worker. Keep that terminal open; Ctrl-C
stops those backend processes. If the isolated environment is unavailable, use
the installation commands in `configs/experiments/issue70/README.md`.

In terminal 2:

The repaired **preflight-005 already passed all 241 tasks** in this workspace.
Keep the backend processes running and proceed directly to the collection
command below. Do not rerun an already-used preflight attempt: outputs are
preserved and the command intentionally refuses to overwrite them.

```bash
source ~/cd_vlaplan
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
python scripts/collect_modality_scene_assets.py --dry-run --workers 4
python scripts/collect_modality_scene_assets.py --preflight --workers 4
```

The dry-run inspects the complete source inventory and physically replays five
representative/regression task groups without HTTP or scene-file output. Add `--full-replay`
to replay all selected tasks without rendering. This was exercised over all
241 task groups: **51,208 distinct states and 78,230 decision bindings**, zero
transition-replay failures. The earlier ~44,759-state inventory omitted generated
successors absent from the compact additive snapshots; it was not full coverage.

The real preflight renders the initial state plus one supplied transition for
every selected task, checks interpretation/stage binding and unresolved geometry,
and preserves exact task/goal metadata. It may find further profile compatibility
problems; it is not a guarantee that every later search state will render.

**Only after the complete preflight returns PASS**, run:

```bash
python scripts/collect_modality_scene_assets.py --collect --workers 4
```

Collection checks that exact predecessor attempt, complete task coverage, and
128px configuration before starting. It replays and renders all root-to-node
leaf paths needed to cover the scene catalog, including non-solution branches.
The full collection is intentionally left to the operator; it may take a long
time. Each task/path reports progress, elapsed time and completed unique frames;
the parent reports ETA and a heartbeat at most ten seconds apart while waiting.
The endpoint mapping is recorded. These CPU/backend jobs do not launch torch.

If a task fails, no more tasks are launched after the failure is observed;
already-running tasks finish. Completed task results are journaled immediately,
and the aggregate cannot PASS with partial coverage. Exit 2 means VALID_STOP;
exit 1 means INVALID. Preserve failed outputs; a new run needs a new matching
attempt/output authorization in a successor config. There is no overwrite or
integrity-check mode.

## What is stored

Each task has one `frames/state-NNNNNN.png` per distinct replayed state, reused
across its decisions and additive settings. Visual and multimodal consumers
reference the same assets. Temporary duplicate path frames are removed by the
owned temporary-directory lifecycle. No 1024px scene copies are stored.

The catalog records every state's atoms/fluents, its first replayed parent/action,
decision-to-state/successor/candidate bindings, source trace paths, task/static
context, **the complete canonical goal formula**, and supplied Action Sequences.
VFGs and catalogs are gzip-compressed; no hashes, file comparisons or regeneration
comparisons are introduced. PNG compression is lossless. VFGs and metadata also
consume disk space and must be included in eventual usage estimates.

The renderer-only 15-puzzle compatibility profile is explicit: original profiles
expect unary position facts, whereas these tasks have typed positions. Positions
are obtained from authoritative type facts; the declared grid-name convention
is checked against the actual neighbor graph. A local animation profile lays out
that grid without modifying the PDDL or supplied actions. Source/used profile
paths and the transformation name are retained. No GPL backend source is copied
or edited. The additional renderer-only compatibility bindings are documented
below; remaining profiles retain their frozen definitions.

## Stored scenes versus VLM observations

128px scenes can be scaled up when composing VLM inputs, but upscaling does not
restore tiny lost labels. Complete relation annotations must be drawn from the
exact semantic metadata at the qualified input resolution, not downsampled to
128px and enlarged again. Keep the current-state image separate from its
successor binding; do not expose future images before the corresponding operation.

This stage deliberately reports `model_input_ready: false`,
`partial_goal_images_complete: false`, and `scientific_completion: false`.
Even a complete `scene_asset_completion: true` is **not** a full #72 or corpus
release PASS. The dense annotation layout and partial-goal visual encoding,
including Snake/Sokoban goal forms, still need qualification. Exact negative or
other constraints are retained as formulas, never silently replaced with a
positive-goal image. Training remains blocked until the matched view/corpus
gates pass.

## Retained development evidence

The two-process localhost smoke succeeded at
`outputs/modality_phase/issue72-scenes128-v1/smoke-005/report.json`:
three representative task groups, six 128px frames, correct supplied transitions.
The corrected puzzle scenes were visually inspected. Earlier smoke attempts are
retained: the initial submission-only pass missed unresolved coordinates;
subsequent stops exposed profile/parser compatibility issues and drove fixes.
Those are not production passes. Full preflight has now passed (see below);
full scene collection has not been run.

### Storage/Grid repair after preflight-001

The operator's first full preflight stopped after nine tasks: seven passed,
Storage had unresolved depot/hoist positions, and Grid rendered symbolic shape
categories as default spatial nodes. That attempt and report are preserved.

Storage now binds the retained profile to actual typed depot/container/area/hoist
objects and area containment, with row widths derived from compartment counts.
Grid binds declared shape categories to distinct existing icons, keeps categories
non-spatial, and explicitly assigns the same icon to matching keys and locks.
The collector validates those Grid icon associations as well as coordinates.
Original PDDL, actions, and 128px output dimensions are unchanged.

The five-task live regression smoke passed with four backend workers at
`outputs/modality_phase/issue72-scenes128-v1/smoke-007/report.json`, including
both failed tasks. Profile generation was also checked for all 13 Storage and
15 Grid groups in the frozen panel; this is not full render qualification.

That repair used preflight-002, which subsequently exposed additional domains.

### Complete-panel repair after preflight-002

The diagnostic preflight-003 exercised all 241 tasks: 185 passed and 56 stopped.
Failures affected Logistics (15), Depot (16), Driverlog (12), Freecell (11),
and Sokoban (2). All earlier attempts remain untouched.

- Logistics: bind static cities/locations using authoritative `in-city` facts.
- Depot/Driverlog: bind typed spatial roots rather than waiting for absent unary
  place/location facts. Original dynamic `at`, `on`, `in`, and driving rules remain.
- Freecell: typed counters and suits are non-spatial symbols, not unresolved
  default sprites. Card sprites remain spatial.
- Sokoban: the legacy backend substitutes `?ply` inside `?ply-from`, producing
  incorrect grounded delete effects. A renderer-only domain copy alpha-renames
  variables to equal-length names. Original PDDL, action argument order, and
  authoritative planning replay remain unchanged; the transformation is recorded.

The full four-worker localhost **preflight-004 passed 241/241 tasks**, rendering
482 frames at 128 × 128 in 19.62 seconds. This renders the initial state and first
transition per task, not all 51,208 catalog states. Representative repaired scenes
were visually inspected; small or overlapping labels still require the separately
qualified annotation views and are not evidence of training readiness.

Defaults now reference the completed **preflight-004** and unused **collect-003**.
Run `python scripts/collect_modality_scene_assets.py --collect --workers 4` next;
the existing backend processes need not restart. Later-state rendering remains
subject to the same semantic checks and stop behavior.

For debugging future failures, `--preflight --diagnostic-continue` visits the full
panel even after a failure. It never turns a failed or partial run into PASS and
is not allowed with collection. A new run still requires a new attempt/output.

### Freecell covered-home repair and successor collection

`collect-003` stopped after 99 complete tasks and one Freecell failure. The
planning state was valid: when a second card enters a foundation, `home` ceases
to name the previous top card. The retained profile left that covered card with
no position rule. This only appears later than the first-edge preflight.

The renderer-only Freecell domain now records `coveredhome` when an action
removes the previous `home` fact. A matching profile rule keeps that card at its
foundation position, underneath the current top and without its label. Original
domain/problem files and authoritative planning states are unchanged. The render
copy and named transformation are retained alongside them. This is explicit
display bookkeeping, not a change to the search task or ignored geometry errors.

Defaults now use completed **preflight-005** and unused **collect-004**. The
configured `reuse_collection` references `collect-003`: 99 PASS/complete task
catalogs (19,839 frames) are reused by their existing paths, not copied. Failed
or partial tasks and the changed Freecell domain are not reused. Source task
scope and coverage must match; an INVALID report cannot supply reused results.
The predecessor report, catalogs and frames are never overwritten. Keep
`collect-003` available because the successor references those assets.

Run:

```bash
python scripts/collect_modality_scene_assets.py --collect --workers 4
```

It logs `reuse_plan` with 99 reused tasks and 142 tasks to render, then starts
completion counts from 99/241. ETA uses newly rendered tasks rather than counting
reused tasks as instantaneous rendering. Task/path progress and heartbeats remain
enabled. There is no need to rerun preflight or restart the existing backend.
The matching completed preflight is still required before collection can start.

Live regressions include multiple-home paths across all 11 selected Freecell
tasks and the exact previously failing path. The full formerly failing task is
also exercised by an opt-in test, including all 363 catalog states:

```bash
PLANIMATION_SCENE_LIVE=1 pytest -q tests/planning_benchmark/test_freecell_scene_live.py
```

The long successor collection is left to the operator. No full collection PASS,
training-view readiness, or #72 completion is implied by these regression tests.
