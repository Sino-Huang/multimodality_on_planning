# Representative Mapping Verification - 2026-08-11

## Outcome

The frozen representative mapping is materialized, byte-stable on rerun, and consumed by the Planimation adapter. Production mode pins its SHA-256 and row count. No network request was made.

## Frozen artifacts

- Request: 16,822 rows, SHA-256 `13db7cba5fb1cf885bd203ff657e5c7714bda6f832c5970dbfe5a9dee36d0585`.
- Expansion index: 31,171 rows, SHA-256 `46d1e7c1c0a6a133372782e691888840a74f3d3732dd625b5e2d8611fdf5d390`.
- Mapping: 16,822 rows, SHA-256 `3d6ff222e3662319d9429e18e3bd0d33a7ea1aee67a07e6d9b1a25c506ad7de3`.
- Report: SHA-256 `bf20b3da0baf66bae787b7fff7760cae764571a96e8e1b6d2c6bd85c7533b1da`.

## Verification

- Focused mapping and adapter tests: 40 passed (27 RED fail-closed fast-fail tests).
- Relevant Phase 3 regression suite: 198 passed in 9.75 seconds.
- Ruff: all checks passed.
- basedpyright: 0 errors, 0 warnings, 0 notes.
- Staged and unstaged diff checks: passed.
- Six immutable-input checksum checks: passed.
- Mapping generation rerun: identical digest and accepted write-once publication.
- Independent final code review: PASS; no CRITICAL or HIGH blocker remains. Review fixes applied and re-reviewed: mapping digest hoisted out of the per-state loop (`_render_state` receives `mapping_sha256` once), the resume command emits `--production-contract` only with a bound mapping and production mapping expectations, the CLI rejects mapping expectation flags without a mapping path, and non-canonical duplicate request atoms raise `RepresentativeMappingError` instead of leaking `PilotExpansionIndexError`. Parametrized fast-fail tests cover schema, policy, state, binding, source, dropped-row, count, and digest mismatch before render; each asserts the renderer is never invoked (`calls == []`).

## Boundary

Production rendering and replay alignment were not run. The prior authorized remote smoke failed, and this mapping pass did not include renewed authorization for external transmission.
