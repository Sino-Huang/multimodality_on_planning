# Phase 3 Release Verifier

The Planimation verifier has three explicit boundaries: `manifest` validates nonempty pairing provenance and source snapshots; `render` adds nonempty render manifests, exact per-pair frame cardinality, and semantic render receipts; `release` adds all persisted hybrid artifacts and production completion.

Release must never use `read_jsonl` directly for required artifacts because that helper intentionally maps missing files to an empty list. Require the file first, then parse every nonblank line with a stable malformed-file reason. Zero-row split JSONL files are valid only when their manifest-reconciled count is zero.

Release completeness is independently recomputed from eligible pairs: each pair requires exactly one full record and one step record per source-plan action. `production_complete` is necessary but insufficient without this reconciliation.

Release also requires all three `search_traversal_<split>.jsonl` files and their closed persisted schema. Every strict FF/GBFS/IW candidate event must have exactly one valid traversal record; Graphplan raw layers remain outside this visual family.
