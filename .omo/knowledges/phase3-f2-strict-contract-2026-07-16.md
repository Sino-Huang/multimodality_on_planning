# Phase 3 F2 Strict Contract

- Traversal traces reject booleans in integer fields and validate planner-specific scalar and nested successor contracts for `ff`, `gbfs`, `iw`, and `graphplan` without changing the active planner set or Graphplan's nonvisual boundary.
- Hybrid schemas and `validate_vlm_record` share one strict schema builder. It types all root, target, provenance, artifact, render-receipt, and typed-array fields while preserving nullable zero-action event actions.
- `verify_planimation_vlm.py` recursively validates persisted full and step schema semantics per JSONL record. This prevents a persisted nested type drift from passing release merely because root `type`, `additionalProperties`, and `record_type` still look valid.
- Evidence: `.omo/evidence/phase3-f2-strict-contract-2026-07-16.json` records the focused 61-test, typecheck, compile, trace CLI, and release CLI results.
- F1 extends the same schema builder and recursive persisted-schema release check to `search_traversal_record`, including nullable parent/action fields and event-versus-state-asset provenance.
