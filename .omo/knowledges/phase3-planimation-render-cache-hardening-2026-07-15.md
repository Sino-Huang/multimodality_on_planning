# Phase 3 Planimation Render Cache Hardening

- Resolve Planimation profiles from `src/data_collect/configs/curriculum_15_domains.yaml` through `load_curriculum_config()`; persist the repository-relative configured path and its SHA-256, never a historical absolute render-result path.
- Cache reuse is a validation operation, not an existence check. Bind the key to schema, domain/problem/profile/state content, renderer identity, and renderer configuration; validate result metadata, derived PDDL replay state, VFG structure/hash, PNG decode/dimensions/hash, and nontransparent-pixel QA before returning a hit.
- Validate every ZIP member before any write. Reject traversal, absolute or escaping targets, symlinks, non-PNG payloads, and bounded-resource violations. The Phase 1 compatibility extractor delegates to the same safe boundary.
