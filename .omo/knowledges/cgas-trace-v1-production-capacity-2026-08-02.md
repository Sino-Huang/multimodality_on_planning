# CGAS trace-v1 production capacity

## Finding

`scripts/phase3/cgas_characterization_rows.py` overrides the repository default `max_trace_steps=10000` with `max_trace_steps=1`. BFS and IW therefore mark a successful multi-event search as truncated even when all unchanged search limits permit the plan.

From a stable hand-empty Blocksworld initial state, adding a missing partial-goal `on(x,y)` edge needs at least two primitive actions. The same lower bound applies between different complete stable states. Consequently, nontrivial complete or historical partial-goal candidates cannot be paired-exact under the trace-v1 one-event persistence override.

## Approved resolution

- Preserve trace-v1 fixture bytes, verifier behavior, and release digest exactly.
- Use historical partial goals for production candidates.
- Add separately versioned, persistence-only `cgas_trace_contract_v2` with bounded-memory canonical event streaming and no successful truncation.
- Require exact external owner approval of the trace-v2 migration packet before production characterization.
- Keep search, plan, grounding, action, IW-width, recovery, paired-exact, selector, and quota contracts unchanged.

## Candidate mathematics

For four objects with complete stable initial states and partial `on(...)` goals, the finite catalog has 600 raw positions, 228 shared-renaming pair orbits, 18 task-solved orbits, and 210 nontrivial candidates. Eight- and twelve-object streams have finite raw capacities 19,514,880 and 2,840,000,486,400 and must be traversed lazily with deterministic cursors.
