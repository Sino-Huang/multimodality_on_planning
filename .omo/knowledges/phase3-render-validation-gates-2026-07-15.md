# Phase 3 Render Validation Gates

- Todo 6 treats a render receipt as valid only when stage-zero VFG sprites have numeric, in-canvas, noncoincident bounds and every expected sprite has at least 1% non-background coverage in the decoded PNG.
- Plan records use only contiguous pre-action frames. The terminal render is diagnostic; a zero-action case uses one initial/terminal full frame and emits no next-action rows.
- `build_vlm_records` independently rechecks relative frame/trace references, hashes, and semantic metrics before records are constructed.
