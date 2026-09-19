# Scene-only state representation proposal

The user requested removing the symbolic annotation blocks from current-state
PNGs to test visual understanding. The old annotated-state view remains a valid
historical text-in-images baseline, but it is not the requested scene-only input.

A native renderer prototype now reads retained replay-bound VFGs, preserving all
planning traces and original 128px assets. It draws large scenes with 24px object
identity labels, places labels above later sprites, and gives the robot a
contrasting colour. The latter fixes a concrete Visitall defect: its robot was
previously tinted identically to the visited cell and was invisible. These are
scene markings, not lists of symbolic state predicates.

Proposed observation: static task context and explicit partial-goal constraints,
plus scene-only initial and current states. The initial state must not remain
printed as facts on the task-context pages if the intended condition requires
visual state perception. Retain identical candidate and Search Memory content
across modalities; these are still rich symbolic inputs, so call this scene-only
state within the shared planning interface, not image-only end-to-end planning.
The multimodal condition pairs these same scenes with symbolic state text.

Current status: renderer prototype and bounded previews only. No replacement
training observations or new visual adapters have been activated. Twelve source
domains were previewed. An initial drawing-description alias check covered five
representative catalogs but is not proof of complete perceptual state coverage;
the invisible Visitall robot illustrates its limits. Full bindings, input-token
measurements, processed preview review and fresh GPU admission remain necessary
before using this representation for training. Current text adapters can only
be reused if their exact inputs, targets and training settings remain unchanged.

The original cumulative clock is retained. Qualification has used 3,043.36/3,600
seconds and training/development 1,512.34/18,000 seconds. There is no implicit
budget reset or training-completion claim for the eight held visual cells.

The Blocksworld scene-only prototype for the state raised by the user is at
`outputs/matched_modalities/scene-only-preview-final/blocksworld-730060/frame_000.png`.
It can be reproduced with `scripts/preview_scene_only_view.py`; the agent ran it.
