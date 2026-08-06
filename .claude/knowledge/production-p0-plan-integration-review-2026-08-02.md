# Production P0 plan integration review

- A bounded candidate bootstrap must not be the only enumeration interface. Feedback-driven characterization requires a pure `(object_count,start_rank,count)` range API whose immutable artifacts can advance beyond the bootstrap prefix without owning the consumption cursor.
- Bootstrap ranges must use the same quota boundaries as the characterization runner. A single `[0,prefix)` artifact conflicts with later exact quota requests when overlapping differently bounded slices are forbidden.
- A bootstrap ceiling is not a terminal stream boundary. Materialize only complete quota batches below the ceiling, except for a short remainder ending at true finite capacity; for ceiling 600 this yields frontiers `{4:600,8:594,12:558}`.
- Post-completion QA of old immutable rounds needs explicit historical replay semantics: verify the requested checkpoint and feedback as ancestors of the current chain, return read-only success, and never repoint the current index backward.
- A journal state describes durable intent, but recovery must also enumerate filesystem-only windows between a namespace mutation and installation of the successor journal generation. In particular, active `prepared` may coexist with the completed tree exchange, and active `verified` may coexist with the completed candidate-to-backup rename.
- Final manual QA is executable only when every command, path, and lifecycle prerequisite is resolved. A digest-bound current-checkpoint index can remove unknown final-round placeholders while preserving immutable checkpoints.
