"""Read-only arithmetic for the owner's quota decision, plus the cost basis behind it.

Recomputes every number from immutable on-disk artifacts, the live selector constants,
and the two measurement reports produced beside this file. Asserts internal cross-checks,
prints a human-readable derivation, and writes a canonical ``quota-options.json``.

This script computes ARITHMETIC ONLY. It does not recommend a quota vector and it does
not alter one. The worker is forbidden by the plan from weakening quotas; the options
below exist so the owner can price each choice, not so the worker can pick one.

Reads only. Creates no checkpoint, trace, cursor, selector result, or process.

Usage:
    source ~/cd_vlaplan && python .claude/evidence/production-p0-corpus-experiment-readiness/\
task-4/owner-decision-packet/derive_quota_options.py
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path("/data/scratch/projects/punim0478/sukaih/multimodality_on_planning")
HERE = ROOT / ".claude/evidence/production-p0-corpus-experiment-readiness/task-4/owner-decision-packet"

CHECKPOINT_1 = ROOT / "tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json"
COMBINATORICS = ROOT / "tmp/cgas-p0-candidates/reports/combinatorics.json"
EXHAUSTION = ROOT / "tmp/cgas-p0-candidates/reports/exhaustion.json"
ELIGIBILITY = HERE / "corpus-eligibility.json"
GROWTH = HERE / "trace-event-growth.json"

FREE_BYTES_AT_CAPTURE = 1.4 * 1000**4  # df on the project path: 11T size, 8.7T used, 1.4T avail
ROUND_1_HOURS = (15, 25)


def canonical(payload: object) -> bytes:
    text = json.dumps(payload, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return text.encode() + b"\n"


class _Tee:
    """Mirror everything printed to stdout into quota-options.txt."""

    def __init__(self, stream: object) -> None:
        self._stream = stream
        self._captured: list[str] = []

    def write(self, text: str) -> int:
        self._captured.append(text)
        return self._stream.write(text)  # type: ignore[attr-defined,no-any-return]

    def flush(self) -> None:
        self._stream.flush()  # type: ignore[attr-defined]

    @property
    def text(self) -> str:
        return "".join(self._captured)


def main() -> int:
    tee = _Tee(sys.stdout)
    sys.stdout = tee  # type: ignore[assignment]
    try:
        return _derive()
    finally:
        sys.stdout = tee._stream  # type: ignore[assignment]
        (HERE / "quota-options.txt").write_text(tee.text, encoding="utf-8")


def _derive() -> int:
    sys.path.insert(0, str(ROOT))
    from scripts.phase3.cgas_partition_contracts import (  # noqa: PLC0415
        EXPECTED_OBJECT_COUNTS,
        EXPECTED_ROW_COUNT,
        EXPECTED_SPLIT_COUNTS,
    )

    checkpoint = json.loads(CHECKPOINT_1.read_text())
    combinatorics = json.loads(COMBINATORICS.read_text())
    exhaustion = json.loads(EXHAUSTION.read_text())
    eligibility = json.loads(ELIGIBILITY.read_text())
    growth = json.loads(GROWTH.read_text())

    accounting = [json.loads(line) for line in checkpoint["accounting"]["canonical_jsonl"].splitlines() if line]
    reservoir = [json.loads(line) for line in checkpoint["reservoir"]["canonical_jsonl"].splitlines() if line]

    per_stream: dict[int, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for row in accounting:
        per_stream[row["object_count"]][row["status"]] += 1
    object_count_of = {row["candidate_id"]: row["object_count"] for row in accounting if row["status"] == "emitted"}
    paired = collections.Counter(object_count_of[row["candidate_id"]] for row in reservoir)

    streams = (4, 8, 12)
    consumed = {n: sum(per_stream[n].values()) for n in streams}
    emitted = {n: per_stream[n]["emitted"] for n in streams}
    exact = {n: paired[n] for n in streams}
    total_emitted = sum(emitted.values())
    total_exact = sum(exact.values())

    assert total_exact == checkpoint["reservoir"]["row_count"], "paired-exact does not sum to reservoir row_count"
    assert consumed == {n: EXPECTED_OBJECT_COUNTS[n] for n in streams}, "round 1 did not consume exactly the quota vector"

    print("=" * 78)
    print("OWNER QUOTA DECISION - READ-ONLY ARITHMETIC (NOT A RECOMMENDATION)")
    print("=" * 78)
    print()
    print("-- live selector constants (scripts/phase3/cgas_partition_contracts.py) --")
    print(f"  EXPECTED_ROW_COUNT     = {EXPECTED_ROW_COUNT}")
    print(f"  EXPECTED_SPLIT_COUNTS  = {dict(sorted(EXPECTED_SPLIT_COUNTS.items()))}")
    print(f"  EXPECTED_OBJECT_COUNTS = {dict(sorted(EXPECTED_OBJECT_COUNTS.items()))}")
    print()

    # ---- measured rates --------------------------------------------------------------
    print("-- round-1 measured rates, recomputed from checkpoint 1 --")
    print(f"  {'n':>3s} {'consumed':>9s} {'emitted':>8s} {'exact':>6s} {'exact/emitted':>14s} {'exact/consumed':>15s} {'required':>9s}")
    yield_emitted: dict[int, float] = {}
    yield_consumed: dict[int, float] = {}
    for n in streams:
        yield_emitted[n] = exact[n] / emitted[n]
        yield_consumed[n] = exact[n] / consumed[n]
        print(
            f"  {n:3d} {consumed[n]:9d} {emitted[n]:8d} {exact[n]:6d}"
            f" {yield_emitted[n] * 100:13.1f}% {yield_consumed[n] * 100:14.1f}% {EXPECTED_OBJECT_COUNTS[n]:9d}"
        )
    print(f"  {'ALL':>3s} {sum(consumed.values()):9d} {total_emitted:8d} {total_exact:6d}"
          f" {total_exact / total_emitted * 100:13.1f}% {total_exact / sum(consumed.values()) * 100:14.1f}% {EXPECTED_ROW_COUNT:9d}")
    print()
    print("  exact/consumed is the decision-relevant rate: disk and wall-clock scale with")
    print("  ranks CONSUMED, not with candidates emitted. Duplicates and subset-solved")
    print("  candidates are rejected before characterization and cost almost nothing.")
    print()

    # ---- which universes are open ----------------------------------------------------
    print("-- which streams can still be extended --")
    universe_4 = combinatorics["four_object"]["retained_nontrivial_ids"]
    for n in streams:
        stream = exhaustion["streams"][str(n)]
        note = f"CLOSED at {universe_4} nontrivial identities" if stream["exhausted"] else "open"
        print(f"  n={n:2d}  capacity {stream['capacity']:>15,}  frontier {stream['frontier']:>4}  exhausted={str(stream['exhausted']):5s}  {note}")
    assert exhaustion["streams"]["4"]["exhausted"] is True, "4-object stream is no longer exhausted"
    assert exhaustion["streams"]["8"]["exhausted"] is False and exhaustion["streams"]["12"]["exhausted"] is False
    print()
    print("  Only n=4 is combinatorially blocked. n=8 and n=12 have effectively unbounded")
    print("  capacity, so their quotas are a COST question, not a feasibility question.")
    print()

    # ---- cost basis ------------------------------------------------------------------
    bfs_bytes = eligibility["by_planner"]["bfs"]["total_bytes"]
    bfs_records = eligibility["by_planner"]["bfs"]["total_records"]
    bytes_per_emitted = bfs_bytes / total_emitted
    bytes_per_consumed = bfs_bytes / sum(consumed.values())
    per_event_v21 = max(growth[key]["other_bytes"] / growth[key]["events"] for key in growth)
    projected_corpus = bfs_records * per_event_v21

    print("-- cost basis, from the measurement reports beside this script --")
    print(f"  round-1 BFS corpus                 {bfs_bytes / 2**40:.2f} TiB over {bfs_records:,} events")
    print(f"  per emitted candidate              {bytes_per_emitted / 2**30:.2f} GB")
    print(f"  per rank consumed                  {bytes_per_consumed / 2**30:.2f} GB")
    print(f"  free on the project quota          {FREE_BYTES_AT_CAPTURE / 2**40:.2f} TiB")
    print(f"  round-1 wall clock                 {ROUND_1_HOURS[0]}-{ROUND_1_HOURS[1]} h")
    print()
    print(f"  under a v2.1 that drops the three reconstructible snapshot fields:")
    print(f"    non-snapshot bytes per event     {per_event_v21:,.0f} B (worst of the two scanned streams)")
    print(f"    projected corpus for round 1     {projected_corpus / 2**30:.1f} GB")
    print(f"    reduction                        {bfs_bytes / projected_corpus:.0f}x")
    print()

    rounds_that_fit_v2 = FREE_BYTES_AT_CAPTURE / bfs_bytes
    print(f"  A further round comparable to round 1 needs ~{bfs_bytes / 2**40:.2f} TiB against"
          f" {FREE_BYTES_AT_CAPTURE / 2**40:.2f} TiB free.")
    print(f"  Rounds that fit before the quota is exhausted: {rounds_that_fit_v2:.2f}")
    print("  => round 2 CANNOT complete at trace-v2 sizes. It would fill the quota partway through.")
    print()

    ineligible_bytes = eligibility["contract_ineligible_bfs"]["bytes"]
    print(f"  Reclaimable now by dropping the {eligibility['contract_ineligible_bfs']['files']} contract-ineligible"
          f" BFS streams: {ineligible_bytes / 2**40:.2f} TiB")
    print(f"  Free after that reclamation: {(FREE_BYTES_AT_CAPTURE + ineligible_bytes) / 2**40:.2f} TiB"
          f" -> {(FREE_BYTES_AT_CAPTURE + ineligible_bytes) / bfs_bytes:.2f} further trace-v2 rounds")
    print()

    # ---- option arithmetic -----------------------------------------------------------
    print("=" * 78)
    print("OPTIONS - ARITHMETIC ONLY, NONE OF THESE IS APPROVED OR RECOMMENDED")
    print("=" * 78)
    print()

    expected_4_final = round(universe_4 * yield_emitted[4])
    ceiling_4 = exact[4] + (universe_4 - emitted[4])

    options: dict[str, object] = {}

    print("OPTION A - keep EXPECTED_ROW_COUNT=481, rebalance EXPECTED_OBJECT_COUNTS")
    print(f"  n=4 cannot exceed {ceiling_4} (absolute ceiling) and is expected to land near {expected_4_final}.")
    print("  Whatever is removed from n=4 must be added to n=8 and/or n=12. Cost of the shift:")
    print()
    print(f"  {'n=4 target':>11s} {'shift':>7s} {'if to n=8':>26s} {'if to n=12':>26s}")
    print(f"  {'':>11s} {'':>7s} {'ranks':>12s} {'v2.1 GB':>13s} {'ranks':>12s} {'v2.1 GB':>13s}")
    option_a: list[dict[str, object]] = []
    for target_4 in (ceiling_4, 100, expected_4_final, 14):
        shift = EXPECTED_OBJECT_COUNTS[4] - target_4
        row: dict[str, object] = {"n4_target": target_4, "shift": shift}
        cells = []
        for n in (8, 12):
            extra_exact = shift + (EXPECTED_OBJECT_COUNTS[n] - exact[n])
            ranks = extra_exact / yield_consumed[n]
            disk = ranks * (projected_corpus / sum(consumed.values()))
            row[f"n{n}_ranks"] = round(ranks)
            row[f"n{n}_v21_bytes"] = round(disk)
            cells.append(f"{ranks:12,.0f} {disk / 2**30:12.1f}G")
        print(f"  {target_4:11d} {shift:7d} {cells[0]:>26s} {cells[1]:>26s}")
        option_a.append(row)
    print()
    print("  'ranks' is the additional ranks that stream must consume to reach its own quota")
    print("  PLUS absorb the shift, at that stream's measured exact/consumed rate.")
    print()
    options["option_a_rebalance"] = option_a

    print("OPTION B - keep EXPECTED_OBJECT_COUNTS proportions, lower EXPECTED_ROW_COUNT")
    print("  The binding stream is n=4. Scaling the whole vector by n=4's achievable count:")
    print()
    print(f"  {'basis':>22s} {'n=4':>6s} {'scale':>7s} {'n=8':>6s} {'n=12':>6s} {'total rows':>11s}")
    option_b: list[dict[str, object]] = []
    for label, n4 in (("absolute ceiling", ceiling_4), ("expected at 15.9%", expected_4_final), ("achieved in round 1", exact[4])):
        scale = n4 / EXPECTED_OBJECT_COUNTS[4]
        n8 = round(EXPECTED_OBJECT_COUNTS[8] * scale)
        n12 = round(EXPECTED_OBJECT_COUNTS[12] * scale)
        print(f"  {label:>22s} {n4:6d} {scale:7.3f} {n8:6d} {n12:6d} {n4 + n8 + n12:11d}")
        option_b.append({"basis": label, "n4": n4, "scale": round(scale, 6), "n8": n8, "n12": n12, "total": n4 + n8 + n12})
    print()
    print(f"  Any of these also breaks EXPECTED_SPLIT_COUNTS {dict(sorted(EXPECTED_SPLIT_COUNTS.items()))},")
    print(f"  which sums to {sum(EXPECTED_SPLIT_COUNTS.values())} and would need rebalancing in the same edit.")
    print()
    options["option_b_scale_down"] = option_b

    print("OPTION C - accept fail-closed termination")
    print("  No constant changes. Todo 4 terminates as proven-infeasible and the plan records")
    print("  finite exhaustion of the 4-object universe. Cost: zero compute. Consequence: no")
    print(f"  481-row population, so Todos 5-16 and F1-F4 stay dependency-gated permanently.")
    print()
    options["option_c_fail_closed"] = {"constants_changed": 0, "compute_hours": 0, "rows_produced": 0}

    print("=" * 78)
    print("INDEPENDENT OF THE QUOTA DECISION")
    print("=" * 78)
    print()
    print("  Options A and B both require further Todo 3 rounds. At trace-v2 sizes NO further")
    print(f"  round fits ({bfs_bytes / 2**40:.2f} TiB needed vs {FREE_BYTES_AT_CAPTURE / 2**40:.2f} TiB free), so the")
    print("  trace-size items in DECISION.md are prerequisites for A and B, not optional")
    print("  cleanups. Option C is the only path that needs neither.")
    print()

    payload = {
        "rates": {
            str(n): {
                "consumed": consumed[n],
                "emitted": emitted[n],
                "paired_exact": exact[n],
                "yield_per_emitted": round(yield_emitted[n], 6),
                "yield_per_consumed": round(yield_consumed[n], 6),
                "required": EXPECTED_OBJECT_COUNTS[n],
                "exhausted": exhaustion["streams"][str(n)]["exhausted"],
            }
            for n in streams
        },
        "four_object": {"universe": universe_4, "ceiling": ceiling_4, "expected_final": expected_4_final, "required": EXPECTED_OBJECT_COUNTS[4]},
        "cost": {
            "round_1_bfs_bytes": bfs_bytes,
            "round_1_bfs_records": bfs_records,
            "bytes_per_emitted": round(bytes_per_emitted),
            "bytes_per_consumed": round(bytes_per_consumed),
            "free_bytes_at_capture": round(FREE_BYTES_AT_CAPTURE),
            "rounds_that_fit_at_v2": round(rounds_that_fit_v2, 3),
            "v21_bytes_per_event": round(per_event_v21),
            "v21_projected_round_bytes": round(projected_corpus),
            "v21_reduction_factor": round(bfs_bytes / projected_corpus, 1),
            "reclaimable_ineligible_bytes": ineligible_bytes,
        },
        "options": options,
        "status": "arithmetic_only_no_recommendation",
    }
    (HERE / "quota-options.json").write_bytes(canonical(payload))
    print(f"-- quota-options.json written ({len(canonical(payload))} bytes) --")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
