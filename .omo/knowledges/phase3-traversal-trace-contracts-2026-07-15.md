# Phase 3 Traversal Trace Contracts

- The active planner set is exactly `ff`, `gbfs`, `iw`, and `graphplan`; reject `bfs` instead of translating it.
- `phase3_traversal_trace_v1` is nested inside the existing outer `phase3_supervised_planning_v1` source-row envelope.
- Build `FrozenSourceIdentity` only from the Todo 1 pairing manifest and reloaded source row. This preserves root, JSONL, physical-line, record-hash, example, and planner provenance without a parallel source identity.
- FF, GBFS, and IW emit `concrete_state` events with a deterministic SHA-256 over sorted recorded atoms. Graphplan layers and extraction are `planner_semantics` and must keep concrete state source/hash unset.
- Use `python -m scripts.phase3.trace_contracts --fixtures tests/phase3/fixtures/traversal_trace_contract_cases.json --report tmp/phase3_task2_trace_projection_report.json` to produce the controlled projection/exclusion evidence report.
