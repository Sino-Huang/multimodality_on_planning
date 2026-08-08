# CGAS Phase 3 pilot-scope decision evidence

The signed v3 checkpoint was analyzed read-only through the existing Gate 0b verifier. Canonical
evidence is under `.claude/evidence/cgas-phase3-pilot-scope/`; checkpoint, approval, contract,
policy, candidate config, selector config/implementation, analyzer, adapter, and release digests are
bound in `report.json`.

The real pool is 281 characterized / 158 paired-exact, split 67/59/32 across 4/8/12 objects with
14/26/9 composition signatures. Plan length is mean 5.215, median 6, max 10. Exact certificate yield
is 1,650 on-plan rows, 60,620 expansion-local opportunities, and 58,970 off-plan-only opportunities.
The predecessor arithmetic's `2 * BFS expansions` was an approximation; the canonical analyzer sums
the separate BFS and IW expansion counts.

Proposed instance-diversity floor: at least 30 candidates per object count; five composition
signatures per count represented at least twice; three initial stack profiles and three goal-edge
levels per count. The current pool passes, with 12 objects tightest at 32 candidates.

At `>=10/cell`, on-plan sizing is 217-325 and cannot use the current pool; off-plan plus the floor is
90 and can. At `>=30/cell`, on-plan is 648-971 and cannot; off-plan is 94-111 and can. The evidence
recommends `>=10`, the 90-instance floor, off-plan harvesting, and conditional reproducibility-only
provenance. These remain owner decisions. Phase 3 was not started, no checkpoint 2 or selector result
was created, and neither characterization root was mutated.
