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
or edited. Other domains continue to use their frozen profiles and can stop
if they are incompatible.

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
Those are not production passes. Neither full preflight nor collection has completed successfully.

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

The default config now uses **preflight-002** and **collect-002**, so rerun the
same preflight command above without deleting anything. The existing backend
processes need not restart. Collection still requires the new complete preflight
PASS; the old stopped report cannot authorize it.
