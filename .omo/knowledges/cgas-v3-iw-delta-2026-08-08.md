# CGAS trace v3 IW novelty delta

M1 slice 2 replaces local IW novelty snapshots with an exact emitted delta and preserves released
v2-shaped fixture certificate semantics.

## Decisions

- The embedded version discriminator for the new IW event shape is the signed v3 `contract_id`,
  `cgas_trace_contract_v3`. This avoids inventing an unsigned `phase3_traversal_trace_v2` literal.
- `phase3_traversal_trace_v1` remains the immutable traversal-fixture version. Required fields and
  types dispatch explicitly on this literal versus `cgas_trace_contract_v3`; field presence is not
  used as a version proxy.
- Expand deltas are computed from the full `novelty_items(state, width)` set before updating the
  running novelty table. Prune events emit an empty delta because they do not update that table.
- `cgas_certificate_contracts.expected_certificate` reads the emitted v3 delta directly and retains
  the clipped-snapshot difference only for released `phase3_traversal_trace_v1` rows.

## Evidence

- RED: 9 focused tests failed before production edits. One later broad-gate failure exposed the
  representative characterization-row digest, for 10 true RED tests total. The direct failures
  included both exact-key surfaces; the indirect failure moved only the derived row digest while
  the characterization kernel AST digest stayed unchanged.
- The seven required suites pass: 68 passed.
- All `test_cgas_*.py` tests report 442 passed, 9 failed. The failures are the same pre-existing
  alternative-profile/blocker-probe and Qwen/release dependency failures as the 439/9 baseline.
- Focused `test_traversal_trace_contracts.py` passes: 17 passed.
- `audit_v3_contract_surface.py` exits 0 at 62 occurrences, 62 classified, 0 unclassified, 0 stale.
- LSP reports no errors in changed production and test modules. The audit script retains the same
  15 pre-existing basedpyright errors documented by slice 1.
- Manual library QA ran native width-2 IW on 21 atoms: the emitted delta contained all 231 features,
  and both certificate and traversal projections accepted the same v3 trace.
- Both release manifests retain SHA-256
  `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`.
- No stream writer, approval cutover, signed v2 artifact, corpus cursor, or checkpoint 2 changed.
