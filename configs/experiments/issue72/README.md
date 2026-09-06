# Issue 72 initial-layout preflight

The scoped **128px scene-asset successor** is now implemented; see
[SCENES128.md](SCENES128.md) for the tested dry-run and parallel preflight/collection
commands. The findings below remain the retained outcome for the old combined
image layout; the successor does not claim its goal/annotation views are ready.

Bulk rendering is blocked. The full selected panel was checked without HTTP,
model/tokenizer calls, image allocation, or frame production. The approximately
four-second attempt produced one 132,331-byte JSON report:

`outputs/modality_phase/issue71-v2/render_preflight/issue72-layout-001/report.json`

Across 241 task groups, 176 initial observations exceed the frozen image
layout, 28 have unsupported goal forms (15 Snake and 13 Sokoban), and 37 pass
this initial-layout check only. The aggregate outcome is INVALID because the
selected sources include unsupported representations. The `invalid_source`
reason means incompatibility with this image contract, not malformed PDDL.
The resource-only failures are individually VALID_STOP. No result here is
scientific completion or permission to collect renders.

The selected 15-puzzle example needs 93 relation rows and 3,628 pixels of
height under the actual layout versus the frozen 1,536. The largest measured
initial observation has 848 rows and requires 29,298 pixels. Enlarging frames
is not the chosen remedy: the supervisor has requested compact frame resolutions
to reduce storage use on the shared server.

To repeat only the read-only feasibility calculation, with per-task progress
and ETA:

```bash
source ~/cd_vlaplan
python scripts/preflight_modality_issue72.py --dry-run
```

Expected exit code: **1**, with the recorded INVALID count. This is an explicit
scientific-contract stop, not a command crash. Exit 2 denotes VALID_STOP with no
INVALID records. Omitting `--dry-run` writes a small report only, never renders;
the completed default attempt already exists and must not be overwritten.
New persisted attempts require new matching gate and authorization files.

The measurement and renderer share the same fact projection and font/layout
calculation. They never truncate facts, shrink labels or allocate an oversized
image to bypass the frozen bounds. Initial-layout success is necessary but not
sufficient: later trace states, profile/path compatibility, processor image
tokens, candidate-state coverage and total storage must still be qualified.

Before any bulk-render command can be offered, a successor contract must:

- keep domain scenes and semantically complete relation/partial-goal information,
  while using a compact layout that fits small images;
- explicitly support the required negative/other goal constraints, or obtain
  approval for a changed task panel; never silently omit them;
- qualify compact frame dimensions and label readability on representative
  tasks, then estimate storage from measured encoded image sizes and unique
  state counts, including VFGs, temporary files and metadata;
- reuse repeated state images and task-level goal assets and share image paths
  between visual and multimodal projections; do not duplicate frames per row.

The supervisor withdrew the previously approved 5 GB cap on 2026-09-07.
There is **no fixed total-byte cap**. Prioritize compact frame resolution,
readability and image reuse; report estimated/actual disk use rather than
stopping at an arbitrary total size. No cap enforcement was implemented.
Storage estimates measure resource consumption only, not artifact integrity.

The compact successor image dimensions still need qualification. Merely
downscaling the overflowing relation panels would make their labels unreadable;
the layout must preserve the required semantics at the selected resolution.
No long run
or full collector has been launched or represented as complete. #72 stays open.
No hashes, checksums, artifact-integrity or regeneration comparisons were added.
