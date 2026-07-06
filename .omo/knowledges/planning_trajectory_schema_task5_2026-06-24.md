# Planning Trajectory Schema Task 5 Notes (2026-06-24)

- Canonical expert trajectory validation is implemented in `examples/planning_benchmark_slice/trajectory_schema.py`; the CLI wrapper is `examples/planning_benchmark_slice/validate_trajectories.py`.
- Records are step-level JSON objects with shared fields at the root and algorithm-specific planner state under one of `bfs`, `fast_forward`, `iterated_width`, or `graphplan`.
- Missing required algorithm fields produce deterministic structured paths, e.g. `bfs.frontier_before`, which downstream tests and evidence commands can assert.
- The validator supports a single `.json`/`.jsonl` file or a directory tree. Valid fixtures live in `tests/fixtures/planning/trajectories/valid/`; invalid missing-field fixtures live in sibling `invalid_missing_*` directories.
- Deterministic canonicalization helpers cover atoms/action strings, novelty tables, mutex pairs, BFS frontier/visited/successors, Fast Forward successor heuristics, and Graphplan layers.
