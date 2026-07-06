## Research plan alignment note

- `doc/research_proposal.md` is the canonical source of truth for the current study scope.
- The updated proposal's P0 algorithm set is: BFS, Fast Forward, Iterated Width, Graphplan.
- The execution plan should include a zero-shot diagnostic gate before large SFT runs.
- P1 should be framed as cross-task transfer, not extra planning algorithms such as Partial Order Planning.
- Preserve repo-specific assumptions while aligning terminology: Blocksworld/Planimation first, Planimation as rendering/environment utility, and minimal coupling to StarVLA core abstractions.
- Task 2 established the frozen symbolic Blocksworld v0 convention: canonical atoms are `predicate(args)` strings (zero-arity predicates use the bare name), legal actions serialize as `name(args)`, and state IDs hash sorted atom lists for order-independent determinism.
- Task 3 zero-shot diagnostics are implemented as offline packaging/scoring only: build 4 algorithms × 4 modalities from the validated Blocksworld fixture, keep `model_facing` separate from `gold_scoring_metadata`, enforce vision/language leakage checks, and score labels as `Pass`, `Algorithmic Error`, `Action Error`, or `Parse Error` without VLM/API/GPU calls.
## 2026-06-24 Task 4 Benchmark Loop

- Phase 2 P0 benchmark evaluation is direct Python, not WebSocket/server-client. The implemented module is `examples/planning_benchmark_slice/benchmark_loop.py`.
- Reuse path for future work: call `load_validated_loop(fixture_path, max_steps=...)`, then use `reset()`, `observe()`, `step(action)`, `run_oracle()`, or `run_scripted(actions)`.
- The benchmark step log is deliberately lighter than the future expert trajectory schema: it records observation, action, pre/post state IDs, legal-action check, post-state atoms, and terminal status only.
