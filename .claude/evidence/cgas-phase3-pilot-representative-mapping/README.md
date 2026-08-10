# Phase 3 Pilot Representative Mapping

## Contract

The owner-approved render-source policy is `replay_then_held_out_then_stable_source_v1`:

1. replay-plan member before non-replay;
2. held-out calibration before train;
3. lower raw rank;
4. lexicographic candidate ID;
5. BFS before IW;
6. lower event sequence;
7. lexicographic row ID.

This policy selects an existing source problem for rendering. It does not select actions, create training targets, or remove the underlying goal ambiguity.

## Frozen bindings

- Request: 16,822 rows, SHA-256 `13db7cba5fb1cf885bd203ff657e5c7714bda6f832c5970dbfe5a9dee36d0585`.
- Expansion index: 31,171 rows, SHA-256 `46d1e7c1c0a6a133372782e691888840a74f3d3732dd625b5e2d8611fdf5d390`.
- Representative mapping: 16,822 rows, SHA-256 `3d6ff222e3662319d9429e18e3bd0d33a7ea1aee67a07e6d9b1a25c506ad7de3`.
- Mapping report: SHA-256 `bf20b3da0baf66bae787b7fff7760cae764571a96e8e1b6d2c6bd85c7533b1da`.

The generated artifacts remain under the ignored local root:

- `tmp/cgas-phase3-pilot-representative-mapping-v1/representative-source-mapping.jsonl`
- `tmp/cgas-phase3-pilot-representative-mapping-v1/representative-source-mapping-report.json`

## Report summary

- Duplicate state groups: 5,339.
- Multi-candidate groups: 4,293.
- Distinct-goal ambiguity groups: 4,282.
- Cross-role groups: 321.
- Replay-containing duplicate groups: 108.
- Maximum group size: 52.
- Selections differing from first physical index row: 325.
- Selected planners: 16,815 BFS and 7 IW.
- Selected roles: 4,844 held-out calibration and 11,978 train.

## Boundary

No Planimation call was made during mapping generation or validation. Production rendering remains blocked pending separately renewed authorization and a successful fresh remote smoke.
