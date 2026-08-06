"""Phase A — planner configuration probe.

Read-only. Measures what IW yields at width 1 and at true iterative width 1->2,
per object count, over the 281 candidate ranks already characterized in round 1.

It does not persist traces, re-run BFS, advance a cursor, write a checkpoint, or
touch any corpus artifact. BFS results are read from the immutable round-1
checkpoint rather than recomputed, so BFS-exactness and BFS plan length come from
the same bytes the infeasibility proof was derived from.

Two hazards the plan records, and how this script handles them:

  - DEFAULT_LIMITS["local_iw_novelty_max_expansions"] is 10,000 while the width-2
    novelty table reaches ~14,365 at n=12, so the cap can trip before novelty
    exhausts and read as a depressed planner rate. This script carries its own
    limits mapping with the cap raised. DEFAULT_LIMITS is contract surface and is
    copied, never mutated.

  - "Exact" is not optimality. It means solved by pure novelty search with no
    plan_recovery fallback, per cgas_characterization_rows._planner_record. Plan
    length against BFS optimal is therefore measured separately.

Usage:
    source ~/cd_vlaplan
    python .claude/evidence/phase-a-planner-configuration-probe/run_probe.py --output <dir>
    python .claude/evidence/phase-a-planner-configuration-probe/run_probe.py --output <dir> --sample 4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.phase3.cgas_candidate_space import build_candidate  # noqa: E402
from scripts.phase3.cgas_partition_contracts import DEFAULT_LIMITS  # noqa: E402
from scripts.phase3.local_iw import run_iterated_width  # noqa: E402
from scripts.phase3.local_iw_novelty import MAX_IW_TRACE_NOVELTY_ITEMS  # noqa: E402
from scripts.phase3.local_planner_types import JSONValue, LocalPlannerRequest  # noqa: E402
from scripts.phase3.pddl import ground_actions, parse_task, replay_plan  # noqa: E402

CHECKPOINT = REPOSITORY_ROOT / "tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json"
CHECKPOINT_SHA256 = "fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853"
DOMAIN = REPOSITORY_ROOT / "modules/pddl-generators/blocksworld/4ops/domain.pddl"

# Raised well above the width-2 novelty-table bound (325 / 3,321 / 14,365 for
# n=4/8/12) so that an exhausted search is a planner result, not a cap artifact.
PROBE_EXPANSION_CAP = 200_000


class ProbeError(RuntimeError):
    pass


class _NoveltyReconstructionSink:
    """Reconstructs the true novelty-table size from the events themselves.

    The trace cannot report it directly: `serialized_novelty_table` clips at
    MAX_IW_TRACE_NOVELTY_ITEMS, so a trace-visible size of 200 means ">=200, true
    value unknown". Each event does carry `state_atoms`, and the planner's table is
    exactly the union of novelty_items(state, width) over expanded states, so
    accumulating those subsets here recovers the true cardinality without touching
    production code. Subset counts are order-independent, so this matches the
    planner's own table size even though the canonical ordering differs.

    Only used on the instrumented subset: attaching any sink makes the planner
    serialize the clipped table on every expansion, which is O(expansions * table).
    """

    __slots__ = ("table", "clipped_peak", "width")

    def __init__(self, width: int) -> None:
        self.table: set[tuple[str, ...]] = set()
        self.clipped_peak = 0
        self.width = width

    def append(self, event: Mapping[str, JSONValue], /) -> None:
        if event.get("decision") != "expand":
            return
        atoms = event.get("state_atoms")
        if isinstance(atoms, list):
            ordered = tuple(sorted(str(atom) for atom in atoms))
            for size in range(1, self.width + 1):
                self.table.update(combinations(ordered, size))
        clipped = event.get("novelty_table_after")
        if isinstance(clipped, list):
            self.clipped_peak = max(self.clipped_peak, len(clipped))


@dataclass(frozen=True, slots=True)
class Row:
    object_count: int
    raw_rank: int
    candidate_id: str
    bfs_exact: bool
    bfs_plan_length: int
    recorded_iw1_exact: bool


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sample", type=int, default=0, help="if >0, probe only N candidates per object count")
    parser.add_argument("--instrument", type=int, default=3, help="candidates per object count to instrument for peak table size")
    args = parser.parse_args(argv)

    digest_before = _digest(CHECKPOINT)
    if digest_before != CHECKPOINT_SHA256:
        raise ProbeError(f"checkpoint digest mismatch: {digest_before}")
    rows = _rows()
    selected = _select(rows, args.sample)
    print(f"probing {len(selected)} candidates ({'sample' if args.sample else 'full sweep'})", flush=True)

    results: list[dict[str, object]] = []
    instrumented: dict[int, int] = defaultdict(int)
    started = time.perf_counter()
    for index, row in enumerate(selected, start=1):
        instrument = instrumented[row.object_count] < args.instrument
        results.append(_probe_one(row, instrument=instrument))
        if instrument:
            instrumented[row.object_count] += 1
        if index % 10 == 0 or index == len(selected):
            print(f"  {index}/{len(selected)}  {time.perf_counter() - started:.1f}s", flush=True)

    digest_after = _digest(CHECKPOINT)
    if digest_after != CHECKPOINT_SHA256:
        raise ProbeError("checkpoint mutated during the probe")

    report = {
        "checkpoint_sha256": digest_before,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "limits": _limits(1),
        "max_iw_trace_novelty_items": MAX_IW_TRACE_NOVELTY_ITEMS,
        "probe_expansion_cap": PROBE_EXPANSION_CAP,
        "read_only": True,
        "results": results,
        "sample_per_object_count": args.sample or None,
        "schema_version": "cgas_phase_a_planner_configuration_probe_v1",
        "summary": _summarize(results),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "probe.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output / "summary.txt").write_text(_render(report), encoding="utf-8")
    print()
    print(_render(report))
    return 0


def _probe_one(row: Row, *, instrument: bool) -> dict[str, object]:
    candidate = build_candidate(row.object_count, row.raw_rank)
    if candidate.candidate_id != row.candidate_id:
        raise ProbeError(f"rank {row.object_count}/{row.raw_rank} no longer rebuilds the recorded candidate")
    with tempfile.TemporaryDirectory(prefix="cgas-phase-a-") as temporary:
        problem_path = Path(temporary) / "problem.pddl"
        problem_path.write_text(candidate.problem, encoding="utf-8")
        task = parse_task(DOMAIN, problem_path)
        grounded, status = ground_actions(
            task,
            max_grounded_actions=DEFAULT_LIMITS["max_grounded_actions"],
            max_grounded_atoms=DEFAULT_LIMITS["max_grounded_atoms"],
        )
        if status is not None:
            raise ProbeError(f"grounding failed for {row.candidate_id}: {status}")
        width_one = _run(task, tuple(grounded), max_width=1)
        escalated = _run(task, tuple(grounded), max_width=2)
        peak = _peak_novelty_table(task, tuple(grounded)) if instrument else None
    return {
        "bfs_exact": row.bfs_exact,
        "bfs_plan_length": row.bfs_plan_length,
        "candidate_id": row.candidate_id,
        "escalated": escalated,
        "object_count": row.object_count,
        "peak_novelty_table": peak,
        "raw_rank": row.raw_rank,
        "recorded_iw1_exact": row.recorded_iw1_exact,
        "width_one": width_one,
    }


def _run(task: object, grounded: tuple[object, ...], *, max_width: int) -> dict[str, object]:
    started = time.perf_counter()
    result = run_iterated_width(LocalPlannerRequest("iw", task, grounded, _limits(max_width)))  # type: ignore[arg-type]
    elapsed = time.perf_counter() - started
    replay = replay_plan(task, list(result.plan), grounded_actions=grounded)  # type: ignore[arg-type]
    replay_ok = replay["replay_ok"] is True and replay["goal_satisfied"] is True
    recovered = "plan_recovery" in result.trace
    exact = (not recovered) and result.status.startswith("success") and replay_ok
    return {
        "exact": exact,
        "expansion_count": result.trace.get("expansion_count"),
        "expansion_count_by_width": result.trace.get("expansion_count_by_width"),
        "plan_length": len(result.plan),
        "recovered": recovered,
        "replay_ok": replay_ok,
        "solving_width": result.trace.get("width"),
        "status": result.status,
        "wall_seconds": round(elapsed, 4),
        "width_sequence": result.trace.get("width_sequence"),
    }


def _peak_novelty_table(task: object, grounded: tuple[object, ...]) -> dict[str, object]:
    sink = _NoveltyReconstructionSink(2)
    run_iterated_width(LocalPlannerRequest("iw", task, grounded, _limits(2), sink))  # type: ignore[arg-type]
    true_peak = len(sink.table)
    return {
        "clipped_peak": sink.clipped_peak,
        "saturated": sink.clipped_peak >= MAX_IW_TRACE_NOVELTY_ITEMS,
        "true_peak": true_peak,
        "understated_by": true_peak - sink.clipped_peak,
    }


def _limits(max_width: int) -> dict[str, int]:
    return {
        **DEFAULT_LIMITS,
        "gbfs_max_expansions": PROBE_EXPANSION_CAP,
        "local_iw_escalate": 1 if max_width > 1 else 0,
        "local_iw_max_width": max_width,
        "local_iw_novelty_max_expansions": PROBE_EXPANSION_CAP,
        "local_iw_recovery": 0,
        "local_iw_width": 1,
        "max_expansions": PROBE_EXPANSION_CAP,
        "max_trace_steps": 0,
    }


def _rows() -> list[Row]:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    parsed: list[Row] = []
    for line in checkpoint["characterization"]["canonical_jsonl"].splitlines():
        record = json.loads(line)
        if record.get("status") != "characterized":
            continue
        bfs = record["bfs"]
        parsed.append(
            Row(
                record["object_count"],
                record["raw_rank"],
                record["candidate_id"],
                bfs["exact_search"]["status"] == "exact_solution_replayed",
                bfs["exact_search"]["plan_length"],
                record["iw_width_1"]["exact_search"]["status"] == "exact_solution_replayed",
            )
        )
    return parsed


def _select(rows: list[Row], sample: int) -> list[Row]:
    if sample <= 0:
        return rows
    seen: dict[int, int] = defaultdict(int)
    selected: list[Row] = []
    for row in rows:
        if seen[row.object_count] < sample:
            selected.append(row)
            seen[row.object_count] += 1
    return selected


def _summarize(results: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
    for result in results:
        grouped[int(result["object_count"])].append(result)
    summary: dict[str, dict[str, object]] = {}
    for object_count in sorted(grouped) + ["all"]:  # type: ignore[list-item]
        group = results if object_count == "all" else grouped[object_count]  # type: ignore[index]
        total = len(group)
        w1 = sum(1 for item in group if item["width_one"]["exact"])  # type: ignore[index]
        w2 = sum(1 for item in group if item["escalated"]["exact"])  # type: ignore[index]
        bfs = sum(1 for item in group if item["bfs_exact"])
        drift = sum(1 for item in group if item["width_one"]["exact"] != item["recorded_iw1_exact"])  # type: ignore[index]
        inflated = [
            int(item["escalated"]["plan_length"]) - int(item["bfs_plan_length"])  # type: ignore[index]
            for item in group
            if item["escalated"]["exact"] and item["bfs_exact"]  # type: ignore[index]
        ]
        saturated = sum(
            1 for item in group if isinstance(item["peak_novelty_table"], dict) and item["peak_novelty_table"]["saturated"]  # type: ignore[index]
        )
        instrumented = [item["peak_novelty_table"] for item in group if isinstance(item["peak_novelty_table"], dict)]
        total_expansions = [
            sum(item["escalated"]["expansion_count_by_width"] or [item["escalated"]["expansion_count"] or 0])  # type: ignore[index]
            for item in group
        ]
        w1_expansions = [int(item["width_one"]["expansion_count"] or 0) for item in group]  # type: ignore[index]
        summary[str(object_count)] = {
            "bfs_exact": bfs,
            "bfs_rate": _rate(bfs, total),
            "expansions_width_1_max": max(w1_expansions) if w1_expansions else None,
            "expansions_width_1_mean": round(sum(w1_expansions) / len(w1_expansions), 1) if w1_expansions else None,
            "expansions_width_2_max": max(total_expansions) if total_expansions else None,
            "expansions_width_2_mean": round(sum(total_expansions) / len(total_expansions), 1) if total_expansions else None,
            "expansions_over_default_cap": sum(1 for value in total_expansions if value > DEFAULT_LIMITS["local_iw_novelty_max_expansions"]),
            "instrumented": len(instrumented),
            "novelty_table_saturated": saturated,
            "novelty_true_peak_max": max((int(item["true_peak"]) for item in instrumented), default=None),  # type: ignore[index]
            "novelty_understated_by_max": max((int(item["understated_by"]) for item in instrumented), default=None),  # type: ignore[index]
            "plan_length_inflation_max": max(inflated) if inflated else None,
            "plan_length_inflation_mean": round(sum(inflated) / len(inflated), 3) if inflated else None,
            "plan_length_inflation_optimal": sum(1 for value in inflated if value == 0) if inflated else None,
            "recorded_iw1_disagreements": drift,
            "total": total,
            "wall_seconds_max": round(max(float(item["escalated"]["wall_seconds"]) for item in group), 3) if group else None,  # type: ignore[index]
            "width_1_exact": w1,
            "width_1_rate": _rate(w1, total),
            "width_2_exact": w2,
            "width_2_rate": _rate(w2, total),
        }
    return summary


def _rate(count: int, total: int) -> float | None:
    return round(100.0 * count / total, 1) if total else None


def _render(report: dict[str, object]) -> str:
    summary = report["summary"]
    assert isinstance(summary, dict)
    lines = [
        "Phase A - IW width 1 vs true iterative width 1->2",
        f"checkpoint {report['checkpoint_sha256']}",
        f"expansion cap raised to {report['probe_expansion_cap']} (DEFAULT_LIMITS ships 10,000)",
        f"elapsed {report['elapsed_seconds']}s",
        "",
        f"{'n':>4} {'total':>6} {'BFS':>7} {'IW w1':>8} {'IW w1->2':>9} {'lift':>7} {'inflation':>10} {'slowest':>9}",
    ]
    for key, value in summary.items():
        lift = (
            f"{value['width_2_rate'] - value['width_1_rate']:+.1f}"
            if value["width_1_rate"] is not None and value["width_2_rate"] is not None
            else "-"
        )
        inflation = "-" if value["plan_length_inflation_mean"] is None else f"{value['plan_length_inflation_mean']:+.2f}"
        lines.append(
            f"{key:>4} {value['total']:>6} {value['bfs_rate']:>6}% {value['width_1_rate']:>7}% "
            f"{value['width_2_rate']:>8}% {lift:>7} {inflation:>10} {value['wall_seconds_max']:>8}s"
        )
    lines += ["", "expansions (width-2 run is the sum across every width attempted):"]
    lines.append(f"{'n':>4} {'w1 mean':>9} {'w1 max':>8} {'w2 mean':>9} {'w2 max':>8} {'over 10k cap':>13}")
    for key, value in summary.items():
        lines.append(
            f"{key:>4} {value['expansions_width_1_mean']:>9} {value['expansions_width_1_max']:>8} "
            f"{value['expansions_width_2_mean']:>9} {value['expansions_width_2_max']:>8} "
            f"{value['expansions_over_default_cap']:>13}"
        )
    lines += ["", f"novelty table at width 2 (instrumented subset; trace clips at {report['max_iw_trace_novelty_items']}):"]
    lines.append(f"{'n':>4} {'instr':>6} {'clipped':>8} {'true peak':>10} {'understated by':>15}")
    for key, value in summary.items():
        lines.append(
            f"{key:>4} {value['instrumented']:>6} {value['novelty_table_saturated']:>8} "
            f"{value['novelty_true_peak_max']:>10} {value['novelty_understated_by_max']:>15}"
        )
    disagreements = sum(int(value["recorded_iw1_disagreements"]) for key, value in summary.items() if key != "all")
    lines += ["", f"width-1 reruns disagreeing with the recorded round-1 result: {disagreements}"]
    return "\n".join(lines) + "\n"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
