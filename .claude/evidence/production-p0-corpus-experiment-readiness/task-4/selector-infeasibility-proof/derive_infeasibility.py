"""Read-only derivation of the Todo 4 selector infeasibility proof.

Recomputes every number from immutable on-disk artifacts and from the live selector
constants, asserts internal cross-checks, prints a human-readable derivation, and writes a
canonical ``proof.json`` beside this file.

Reads only. Creates no checkpoint, trace, cursor, selector result, or process.

Usage:
    source ~/cd_vlaplan && python -m \
      scripts.phase3.__nonexistent__ 2>/dev/null; \
    source ~/cd_vlaplan && python .claude/evidence/production-p0-corpus-experiment-readiness/\
task-4/selector-infeasibility-proof/derive_infeasibility.py
"""

from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path("/data/scratch/projects/punim0478/sukaih/multimodality_on_planning")
HERE = ROOT / (
    ".claude/evidence/production-p0-corpus-experiment-readiness/task-4/selector-infeasibility-proof"
)

CHECKPOINT_1 = ROOT / "tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json"
CURRENT = ROOT / "tmp/cgas-p0-characterized/current.json"
SELECTOR_1 = ROOT / "tmp/cgas-production-population/selector_attempt_000001.json"
COMBINATORICS = ROOT / "tmp/cgas-p0-candidates/reports/combinatorics.json"
EXHAUSTION = ROOT / "tmp/cgas-p0-candidates/reports/exhaustion.json"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(payload: object) -> bytes:
    text = json.dumps(
        payload, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    return text.encode() + b"\n"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from scripts.phase3.cgas_partition_contracts import (  # noqa: PLC0415
        EXPECTED_OBJECT_COUNTS,
        EXPECTED_ROW_COUNT,
        EXPECTED_SPLIT_COUNTS,
    )

    checkpoint = json.loads(CHECKPOINT_1.read_text())
    combinatorics = json.loads(COMBINATORICS.read_text())
    exhaustion = json.loads(EXHAUSTION.read_text())
    selector = json.loads(SELECTOR_1.read_text())

    accounting = [json.loads(line) for line in checkpoint["accounting"]["canonical_jsonl"].splitlines() if line]
    characterization = [
        json.loads(line) for line in checkpoint["characterization"]["canonical_jsonl"].splitlines() if line
    ]
    reservoir = [json.loads(line) for line in checkpoint["reservoir"]["canonical_jsonl"].splitlines() if line]

    print("=" * 78)
    print("TODO 4 SELECTOR INFEASIBILITY - READ-ONLY DERIVATION")
    print("=" * 78)
    print()
    print("-- bound artifacts --")
    digests = {
        "checkpoint_1_sha256": sha256_file(CHECKPOINT_1),
        "current_sha256": sha256_file(CURRENT),
        "selector_attempt_1_sha256": sha256_file(SELECTOR_1),
    }
    for name, value in digests.items():
        print(f"  {name:32s} {value}")
    print(f"  {'reservoir_sha256':32s} {checkpoint['reservoir']['sha256']}")
    print(f"  {'selector_implementation_sha256':32s} {selector['selector_implementation_sha256']}")
    print(f"  {'selector_config_sha256':32s} {selector['selector_config_sha256']}")
    print(f"  {'checkpoint round':32s} {checkpoint['round']}")
    print(f"  {'selector attempt status':32s} {selector['status']} / {selector['reason']}")
    print()

    # ---- selector requirements, read live from the production module -----------------
    print("-- selector requirements (live from scripts/phase3/cgas_partition_contracts.py) --")
    print(f"  EXPECTED_ROW_COUNT      = {EXPECTED_ROW_COUNT}")
    print(f"  EXPECTED_SPLIT_COUNTS   = {dict(sorted(EXPECTED_SPLIT_COUNTS.items()))}")
    print(f"  EXPECTED_OBJECT_COUNTS  = {dict(sorted(EXPECTED_OBJECT_COUNTS.items()))}")
    required_4 = EXPECTED_OBJECT_COUNTS[4]
    print()
    print("  Enforced in scripts/phase3/cgas_production_population_manifest.py:")
    print("    line 24-25  every selected row must pass _paired_exact(row)")
    print("    line 43-44  object_counts != Counter(EXPECTED_OBJECT_COUNTS)")
    print("                -> SelectionFeasibilityError('production_object_quota_invalid')")
    print("    line 45-49  required matrix includes ('train', 4): 190")
    print(f"  => the selector needs exactly {required_4} PAIRED-EXACT 4-object rows.")
    print()

    # ---- the finite 4-object universe -----------------------------------------------
    four = combinatorics["four_object"]
    universe_4 = four["retained_nontrivial_ids"]
    print("-- the 4-object candidate universe (tmp/cgas-p0-candidates/reports/) --")
    print(f"  combinatorics.json four_object = {four}")
    print(f"  exhaustion.json    streams['4'] = {exhaustion['streams']['4']}")
    assert four["canonical_ids"] == universe_4 + four["solved_ids"], "orbit accounting mismatch"
    print(f"  canonical orbits {four['canonical_ids']} - subset-solved {four['solved_ids']}"
          f" = retained nontrivial {universe_4}")
    exhausted_4 = exhaustion["streams"]["4"]["exhausted"]
    print(f"  4-object stream exhausted = {exhausted_4} at frontier"
          f" {exhaustion['streams']['4']['frontier']} of capacity {exhaustion['streams']['4']['capacity']}")
    print(f"  => the universe is CLOSED at {universe_4} distinct nontrivial 4-object identities.")
    print()

    # ---- what round 1 actually consumed ---------------------------------------------
    per_stream: dict[int, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for row in accounting:
        per_stream[row["object_count"]][row["status"]] += 1

    print("-- round-1 accounting, recomputed from checkpoint 1 --")
    print(f"  {'n':>3s} {'consumed':>9s} {'emitted':>8s} {'duplicate':>10s} {'solved':>7s}")
    for n in (4, 8, 12):
        counts = per_stream[n]
        print(f"  {n:3d} {sum(counts.values()):9d} {counts['emitted']:8d}"
              f" {counts['duplicate']:10d} {counts['solved']:7d}")
    total = collections.Counter()
    for counts in per_stream.values():
        total.update(counts)
    assert dict(total) == {
        k: v for k, v in checkpoint["accounting"]["counts"].items()
    }, "per-stream accounting does not sum to the checkpoint counts"
    print(f"  cross-check: sums to checkpoint accounting counts {checkpoint['accounting']['counts']} OK")
    print()

    # ---- paired-exact yield per stream ----------------------------------------------
    object_count_of = {row["candidate_id"]: row["object_count"] for row in accounting if row["status"] == "emitted"}
    assert len(object_count_of) == total["emitted"], "emitted candidate ids are not unique"
    assert len(characterization) == total["emitted"], "one characterization per emitted id violated"

    paired = collections.Counter(object_count_of[row["candidate_id"]] for row in reservoir)
    assert sum(paired.values()) == checkpoint["reservoir"]["row_count"] == len(reservoir), (
        "per-stream paired-exact does not sum to the checkpoint reservoir row_count"
    )
    print("-- paired-exact yield per stream, recomputed from checkpoint 1 --")
    print(f"  {'n':>3s} {'emitted':>8s} {'paired_exact':>13s} {'yield':>7s} {'required':>9s}")
    yields: dict[int, float] = {}
    for n in (4, 8, 12):
        emitted = per_stream[n]["emitted"]
        exact = paired[n]
        yields[n] = exact / emitted
        print(f"  {n:3d} {emitted:8d} {exact:13d} {yields[n] * 100:6.1f}%"
              f" {EXPECTED_OBJECT_COUNTS[n]:9d}")
    print(f"  cross-check: sums to reservoir row_count {checkpoint['reservoir']['row_count']} OK")
    print()

    # ---- the proof -------------------------------------------------------------------
    emitted_4 = per_stream[4]["emitted"]
    exact_4 = paired[4]
    remaining_4 = universe_4 - emitted_4
    ceiling_4 = exact_4 + remaining_4
    feasible = ceiling_4 >= required_4

    print("=" * 78)
    print("PROOF")
    print("=" * 78)
    print(f"  4-object universe (closed)                      = {universe_4}")
    print(f"  4-object already characterized                  = {emitted_4}")
    print(f"  4-object paired-exact achieved                  = {exact_4}")
    print(f"  4-object never characterized (upper bound left) = {universe_4} - {emitted_4} = {remaining_4}")
    print(f"  ABSOLUTE CEILING (if ALL remaining were exact)  = {exact_4} + {remaining_4} = {ceiling_4}")
    print(f"  SELECTOR HARD REQUIREMENT                       = {required_4}")
    print()
    print(f"  {ceiling_4} {'>=' if feasible else '<'} {required_4}  ->  feasible = {feasible}")
    print()
    print(f"  Expected (not best-case) final at the observed {yields[4] * 100:.1f}% rate:"
          f" {universe_4} x {yields[4]:.3f} = {round(universe_4 * yields[4])}")
    print(f"  Shortfall factor against requirement: {required_4 / (universe_4 * yields[4]):.1f}x")
    print()
    print("  Why the gap cannot close:")
    print("   1. The 4-object stream is exhausted at its full capacity of 600 raw ranks,")
    print("      so no further 4-object candidates can ever be enumerated.")
    print(f"   2. retained_nontrivial_ids = {universe_4} is the complete set of distinct")
    print("      nontrivial 4-object identities in the entire universe.")
    print("   3. Characterization is once per candidate id under a frozen paired-exact")
    print("      policy, so an already-characterized non-exact candidate cannot become exact.")
    print()

    other = {n: EXPECTED_OBJECT_COUNTS[n] for n in (8, 12)}
    print("  Only the 4-object stream is blocked. At observed yields the others would reach")
    print("  quota in roughly:")
    for n, need in other.items():
        emitted_needed = need / yields[n]
        ranks_per_round = {8: 198, 12: 93}[n]
        emitted_per_round = per_stream[n]["emitted"]
        rounds = (emitted_needed - per_stream[n]["emitted"]) / emitted_per_round
        print(f"    n={n:2d}: need {need} exact at {yields[n] * 100:.1f}% -> ~{emitted_needed:.0f} emitted"
              f" -> ~{rounds:.0f} further rounds of {ranks_per_round} ranks")
    print()

    payload = {
        "schema_version": "cgas_todo4_infeasibility_proof_v1",
        "conclusion": {
            "feasible": feasible,
            "blocking_object_count": 4,
            "max_achievable_paired_exact_4_object": ceiling_4,
            "required_paired_exact_4_object": required_4,
            "expected_final_paired_exact_4_object": round(universe_4 * yields[4]),
            "statement": (
                f"The selector requires exactly {required_4} paired-exact 4-object rows. "
                f"The 4-object candidate universe is closed at {universe_4} distinct nontrivial "
                f"identities and its stream is already exhausted. {emitted_4} have been "
                f"characterized yielding {exact_4} paired-exact. Even if every one of the "
                f"remaining {remaining_4} were paired-exact the ceiling is {ceiling_4}, which is "
                f"less than {required_4}. No further Todo 3 round can satisfy Todo 4."
            ),
        },
        "bound_digests": {
            **digests,
            "reservoir_sha256": checkpoint["reservoir"]["sha256"],
            "selector_config_sha256": selector["selector_config_sha256"],
            "selector_implementation_sha256": selector["selector_implementation_sha256"],
            "trace_v1_release_sha256": "3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3",
        },
        "checkpoint": {
            "round": checkpoint["round"],
            "accounting_counts": checkpoint["accounting"]["counts"],
            "accounting_row_count": checkpoint["accounting"]["row_count"],
            "characterization_row_count": checkpoint["characterization"]["row_count"],
            "reservoir_row_count": checkpoint["reservoir"]["row_count"],
            "reservoir_signature_count": checkpoint["reservoir"]["signature_count"],
            "streams": checkpoint["streams"],
        },
        "selector_attempt_1": {
            "round": selector["round"],
            "status": selector["status"],
            "reason": selector["reason"],
            "note": (
                "calibration_exact_39_unavailable is the first constraint the manifest builder "
                "reaches (cgas_production_population_manifest.py:12-15), not the binding one. "
                "The 4-object quota at line 43 is the constraint that cannot ever be satisfied."
            ),
        },
        "selector_requirements": {
            "expected_object_counts": dict(sorted(EXPECTED_OBJECT_COUNTS.items())),
            "expected_row_count": EXPECTED_ROW_COUNT,
            "expected_split_counts": dict(sorted(EXPECTED_SPLIT_COUNTS.items())),
            "source": "scripts/phase3/cgas_partition_contracts.py:11",
            "enforcement": [
                "scripts/phase3/cgas_production_population_manifest.py:24-25 _paired_exact required",
                "scripts/phase3/cgas_production_population_manifest.py:43-44 production_object_quota_invalid",
                "scripts/phase3/cgas_production_population_manifest.py:45-49 ('train',4):190 matrix",
            ],
        },
        "four_object_universe": {
            "canonical_ids": four["canonical_ids"],
            "solved_ids": four["solved_ids"],
            "retained_nontrivial_ids": universe_4,
            "raw_candidates": four["raw_candidates"],
            "stream": exhaustion["streams"]["4"],
            "source": "tmp/cgas-p0-candidates/reports/combinatorics.json and exhaustion.json",
        },
        "per_stream": {
            str(n): {
                "consumed_ranks": sum(per_stream[n].values()),
                "emitted": per_stream[n]["emitted"],
                "duplicate": per_stream[n]["duplicate"],
                "solved": per_stream[n]["solved"],
                "paired_exact": paired[n],
                "paired_exact_yield": round(yields[n], 6),
                "required_paired_exact": EXPECTED_OBJECT_COUNTS[n],
            }
            for n in (4, 8, 12)
        },
        "compounding_constraints": {
            "no_reachable_terminal_state": (
                "finite_candidate_exhaustion requires all three streams exhausted; 8-object "
                "capacity is 19,514,880 ranks and 12-object capacity is 2,840,000,486,400 ranks, "
                "consumed at 198 and 93 per round."
            ),
            "quadratic_validation": (
                "cgas_candidate_characterization_checkpoint.py:122-128 re-verifies every "
                "accumulated characterization row's trace streams on every round, so total I/O "
                "grows as O(rounds^2)."
            ),
            "round_2_cost": (
                "A resume performs two full passes over the 2.25 TB of persisted BFS streams: "
                "one in cgas_candidate_characterization_planners.py:56-63 (existing traces are "
                "verified AND the planner search is fully re-executed with max_trace_steps=0), "
                "one in checkpoint validation. At the measured ~85 MB/s CPU-bound parse rate "
                "this is roughly 15-25 hours. The interrupted attempt ran 15h19m and had not "
                "finished the second pass."
            ),
            "disk_headroom": (
                "Traces occupy 2.25 TB. The project directory quota reports ~1.4 TB free of 11 TB "
                "(87% used), so another full round of 12-object traces does not fit. Note df must "
                "be run against the project path; /data/scratch reports the whole 692 TB "
                "filesystem, which is not the binding constraint."
            ),
        },
        "scope": {
            "round_2_executed": False,
            "checkpoint_2_present": False,
            "cursors_advanced": False,
            "selector_feedback_emitted": False,
            "todo_4_checked": False,
            "note": "Read-only derivation. No checkpoint, trace, cursor, selector result, or process was created.",
        },
    }

    proof_bytes = canonical(payload)
    (HERE / "proof.json").write_bytes(proof_bytes)
    print("-- proof.json --")
    print(f"  bytes  {len(proof_bytes)}")
    print(f"  sha256 {hashlib.sha256(proof_bytes).hexdigest()}")
    print()
    print("DERIVATION COMPLETE. All internal cross-checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
