# Phase 3 F2 Persisted Contract Remediation

- Persisted pair and state manifests cross a typed JSON boundary in `scripts/phase3/planimation_persisted_contracts.py`; release and pairing-output validation share it.
- Use `type(value) is int` for persisted integer primitives because `isinstance(True, int)` is true in Python. This protects pair sizes and state `step_index` without accepting booleans.
- State success and failed variants must not mix variant-specific fields. `attempts`, `cache_hit`, and failed `derived_problem_path` remain optional because current renderer paths do not emit them uniformly; validate their primitive types whenever present.
- Failed source-plan cardinality records intentionally have no transition. Any state sorting or manifest receipt derivation must use `row.get("transition", {})` for this controlled failure shape.
- Current proof: the focused release/pairing suite passed 50 tests; basedpyright, compileall, LSP, valid release CLI, and bool-corruption release CLI probes all passed their expected outcomes.
