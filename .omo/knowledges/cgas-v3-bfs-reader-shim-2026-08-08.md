# CGAS trace v3 BFS reader shim

Slice 1 of M1 removes `frontier_before`, `frontier_after`, and `visited_after` from
`scripts/phase3/cgas_bfs.py` and reconstructs the certificate projection in
`scripts/phase3/cgas_certificate_contracts.py`.

## Decisions

- Reconstruction is unconditional. The released v2 fixture rows and stripped v3-shaped rows both
  reproduce every released BFS certificate exactly, so version dispatch would add a second path
  without changing semantics.
- `_prior_bfs_visited` is deleted. R4 makes `visited_delta` the current event's enqueued successor
  IDs, plus the root state ID at expansion index 0; preserving the previous-expansion call site
  would be both dead and error-prone.
- The FIFO fold starts from `[expansions[0].state_id]` and applies
  `frontier = frontier[1:] + enqueued` through the selected expansion. At a goal-found-mid-expansion
  event, only recorded successor rows are appended, matching the emitter's early return.

## Evidence

- RED: five focused tests failed before production changes. The complete gates then exposed two
  indirect digest pins, for seven true RED sites total.
- GREEN: the seven-suite gate remains `68 passed`; all `test_cgas_*.py` files are `439 passed,
  9 failed`, with the same nine pre-existing probe/Qwen/release failures as the `436/9` baseline.
- `audit_v3_contract_surface.py` exits 0 at 65 occurrences, 65 classified, 0 unclassified, 0 stale.
- `basedpyright` reports 0 errors on the changed production and test modules. The packet audit
  script retains 15 pre-existing type errors that reproduce from its `HEAD` version.
- `validate_approval` and `ApprovedTraceModel` remain pinned to trace contract v2. No corpus round,
  cursor advance, checkpoint 2, IW emitter change, trace validator change, or writer change occurred.
