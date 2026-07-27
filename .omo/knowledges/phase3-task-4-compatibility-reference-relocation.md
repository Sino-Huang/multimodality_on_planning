# Compatibility Reference Relocation Rule

When relocating Phase 3 compatibility references, keep each destination basename identical to its source basename. `source_root_id` is derived from `Path.name`, so changing the basename changes identity even if the parent relocation is correct.

Strict shell references must match approved output-catalog destinations. Change only the catalog-covered strict trace assignments. Protected roots and every `FRAME_ROOT` stay unchanged.
