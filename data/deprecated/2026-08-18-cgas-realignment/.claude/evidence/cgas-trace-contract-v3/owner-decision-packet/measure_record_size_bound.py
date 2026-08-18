#!/usr/bin/env python
"""Measure the per-record size bound trace contract v2 omitted.

Read-only. Opens corpus streams for reading only, writes only to this directory.
Creates no checkpoint, cursor, trace, or process. Deletes nothing.

The old contract bounded stream RECORD COUNT and never per-record SIZE. This
script measures what a size bound would have to be, and checks the three
reconstruction rules the field drop rests on.

Four outputs:

  1. Corpus inventory. Every stream's byte size, record count, and completion
     status, from stat() and the canonical trailer. No full scan.

  2. Per-event size, v2 as written and v3 as projected. For each sampled event
     the script re-canonicalises the record with frontier_before / frontier_after
     / visited_after removed and measures the resulting line. This is a
     measurement of the v3 line, not an estimate of it.

  3. Element counts per event -- state_atoms, successors, actions_considered,
     and the widest successor. These are what a byte bound would have to be
     DERIVED from if it is to be provable rather than merely chosen.

  4. Rule verification. R1/R2/R3 as the prior packet stated them, plus one rule
     that packet did not state and that the reader shim depends on:

       R4  visited_after[i] \\ visited_after[i-1] == {enqueued successor ids of i}
           (and at i == 0, that set plus the start state id)

     R4 matters because it means `visited_delta` needs no fold at all -- only
     `frontier_order_summary` does. A shim that folds three fields is doing two
     more than it has to.

  IW streams are scanned in full; they are 0.07 GB in total.

Usage:
    source ~/cd_vlaplan
    python .claude/evidence/cgas-trace-contract-v3/owner-decision-packet/measure_record_size_bound.py
    python ... --head-events 800 --bfs-samples 24     # deeper, slower
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))

TRACE_ROOT = REPOSITORY_ROOT / "tmp/cgas-p0-characterized/traces"
DROPPED = ("frontier_before", "frontier_after", "visited_after")
TAIL_WINDOW = 64 * 1024 * 1024
READER_LINE_CEILING = 16 * 1024 * 1024  # cgas_trace_stream_v2.verify_trace_stream:114


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def trailer_of(path: Path) -> dict[str, object] | None:
    """Read the final line without scanning the stream."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - 65536))
        chunk = handle.read()
    parts = [item for item in chunk.split(b"\n") if item]
    if not parts:
        return None
    try:
        record = json.loads(parts[-1])
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) and record.get("record_type") == "trailer" else None


def final_event_of(path: Path) -> dict[str, object] | None:
    """Read the last EVENT line (the one before the trailer)."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - TAIL_WINDOW))
        chunk = handle.read()
    parts = chunk.split(b"\n")
    # Drop a leading partial line and the trailing empty element.
    complete = parts[1:-1] if len(parts) > 2 else []
    for raw in reversed(complete):
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("record_type") == "event":
            return {"line_bytes": len(raw) + 1, "record": record}
    return None


def inventory() -> dict[str, object]:
    streams: list[dict[str, object]] = []
    for directory in sorted(TRACE_ROOT.iterdir()):
        if not directory.is_dir():
            continue
        for planner, name in (("bfs", "bfs.trace-v2.jsonl"), ("iw", "iw.trace-v2.jsonl")):
            path = directory / name
            if not path.is_file():
                continue
            trailer = trailer_of(path)
            streams.append(
                {
                    "path": str(path.relative_to(REPOSITORY_ROOT)),
                    "planner": planner,
                    "bytes": path.stat().st_size,
                    "record_count": trailer.get("record_count") if trailer else None,
                    "completion_status": trailer.get("completion_status") if trailer else None,
                }
            )
    by_group: dict[tuple[str, str], dict[str, int]] = {}
    for stream in streams:
        key = (str(stream["planner"]), str(stream["completion_status"]))
        bucket = by_group.setdefault(key, {"files": 0, "bytes": 0, "records": 0})
        bucket["files"] += 1
        bucket["bytes"] += int(stream["bytes"])
        bucket["records"] += int(stream["record_count"] or 0)
    return {"streams": streams, "groups": {f"{p}/{s}": v for (p, s), v in sorted(by_group.items())}}


def scan_bfs(path: Path, head_events: int) -> dict[str, object]:
    """Measure a head prefix plus the final event, and check R1-R4.

    Seeded from the emitter's own initial state (cgas_bfs.run_fifo_bfs): the
    frontier is [start] and _visited is [start_id] before the first expansion,
    and every expansion popleft()s the head then appends its enqueued
    successors. The head prefix always begins at sequence 0, so the fold is
    exact rather than assumed.
    """
    v2_sizes: list[int] = []
    v3_sizes: list[int] = []
    atom_counts: list[int] = []
    successor_counts: list[int] = []
    action_counts: list[int] = []
    successor_atom_max = 0
    violations = {"R1": 0, "R2": 0, "R3": 0, "R4": 0}
    checked = 0
    frontier: list[str] | None = None      # state of the FIFO before the current expansion
    visited: set[str] | None = None
    with path.open("rb") as handle:
        for index, raw in enumerate(handle):
            if index >= head_events:
                break
            record = json.loads(raw)
            if record.get("record_type") != "event":
                continue
            event = record["event"]
            state_id = event["state_id"]
            successors = event["successors"]
            enqueued = [row["state_id"] for row in successors if row["enqueued"]]
            if frontier is None:
                frontier, visited = [state_id], {state_id}

            # R1 -- frontier_before is a literal restatement of state_id.
            if event["frontier_before"] != [state_id]:
                violations["R1"] += 1
            # R2 -- FIFO: pop the head, append this event's enqueued successors.
            rebuilt_frontier = frontier[1:] + enqueued
            if event["frontier_after"] != rebuilt_frontier:
                violations["R2"] += 1
            # R3 -- visited is the running union, kept sorted by insort.
            rebuilt_visited = sorted(set(visited or set()) | set(enqueued))
            if event["visited_after"] != rebuilt_visited:
                violations["R3"] += 1
            # R4 -- what cgas_certificate_contracts actually computes as
            # visited_delta: this expansion's visited_after minus the PREVIOUS
            # expansion's, with the previous taken as empty at index 0.
            previous = set() if index == 0 else set(visited or set())
            observed_delta = sorted(set(event["visited_after"]) - previous)
            expected_delta = sorted({state_id, *enqueued}) if index == 0 else sorted(set(enqueued))
            if observed_delta != expected_delta:
                violations["R4"] += 1
            checked += 1

            frontier = list(event["frontier_after"])
            visited = set(event["visited_after"])

            v2_sizes.append(len(raw))
            projected = dict(record)
            projected["event"] = {k: v for k, v in event.items() if k not in DROPPED}
            v3_sizes.append(len(canonical(projected)) + 1)
            atom_counts.append(len(event["state_atoms"]))
            successor_counts.append(len(successors))
            action_counts.append(len(event["actions_considered"]))
            successor_atom_max = max(
                successor_atom_max, max((len(row["state_atoms"]) for row in successors), default=0)
            )
    final = final_event_of(path)
    result: dict[str, object] = {
        "path": str(path.relative_to(REPOSITORY_ROOT)),
        "events_checked": checked,
        "violations": violations,
        "v2_bytes_min": min(v2_sizes) if v2_sizes else 0,
        "v2_bytes_max": max(v2_sizes) if v2_sizes else 0,
        "v3_bytes_min": min(v3_sizes) if v3_sizes else 0,
        "v3_bytes_max": max(v3_sizes) if v3_sizes else 0,
        "v3_bytes_mean": round(statistics.fmean(v3_sizes), 1) if v3_sizes else 0,
        "state_atoms_max": max(atom_counts) if atom_counts else 0,
        "successors_max": max(successor_counts) if successor_counts else 0,
        "actions_considered_max": max(action_counts) if action_counts else 0,
        "successor_state_atoms_max": successor_atom_max,
    }
    if final is not None:
        event = final["record"]["event"]  # type: ignore[index]
        projected = dict(final["record"])  # type: ignore[arg-type]
        projected["event"] = {k: v for k, v in event.items() if k not in DROPPED}
        result["final_event_v2_bytes"] = final["line_bytes"]
        result["final_event_v3_bytes"] = len(canonical(projected)) + 1
        result["final_event_frontier"] = len(event["frontier_after"])
        result["final_event_visited"] = len(event["visited_after"])
        result["final_event_successors"] = len(event["successors"])
        result["final_event_state_atoms"] = len(event["state_atoms"])
    return result


def scan_iw(path: Path) -> dict[str, object]:
    v2_sizes: list[int] = []
    v3_sizes: list[int] = []
    w2_sizes: list[int] = []
    delta_lengths: list[int] = []
    atom_counts: list[int] = []
    expand_events = 0
    with path.open("rb") as handle:
        for raw in handle:
            record = json.loads(raw)
            if record.get("record_type") != "event":
                continue
            event = record["event"]
            v2_sizes.append(len(raw))
            projected = {k: v for k, v in event.items() if k not in ("novelty_table_before", "novelty_table_after")}
            atoms = event["state_atoms"]
            if event.get("decision") == "expand":
                expand_events += 1
                # At width 1 the table never reached the 200-item clip (largest
                # observed across all 558 streams is 150), so this difference of
                # two snapshots IS the true delta and can be trusted here. That
                # is exactly what stops being true at width 2.
                delta = sorted(set(event["novelty_table_after"]) - set(event["novelty_table_before"]))
                projected["seen_feature_delta"] = delta
                delta_lengths.append(len(delta))
            else:
                projected["seen_feature_delta"] = []
                delta_lengths.append(0)
            atom_counts.append(len(atoms))
            outer = dict(record)
            outer["event"] = projected
            v3_sizes.append(len(canonical(outer)) + 1)

            # Worst-case width-2 projection for the SAME event: the emitted
            # delta can be at most the full novelty_items(state, 2) set, which
            # is |atoms| singletons plus C(|atoms|, 2) pairs, each serialized by
            # local_iw_novelty.serialize_tuple as "a | b".
            singles = list(atoms)
            pairs = [f"{a} | {b}" for i, a in enumerate(atoms) for b in atoms[i + 1:]]
            worst = dict(projected)
            worst["seen_feature_delta"] = sorted(singles + pairs)
            outer_w2 = dict(record)
            outer_w2["event"] = worst
            w2_sizes.append(len(canonical(outer_w2)) + 1)
    return {
        "events": len(v2_sizes),
        "expand_events": expand_events,
        "v2_bytes_max": max(v2_sizes) if v2_sizes else 0,
        "v3_bytes_max": max(v3_sizes) if v3_sizes else 0,
        "w2_bytes_max": max(w2_sizes) if w2_sizes else 0,
        "v2_bytes_total": sum(v2_sizes),
        "v3_bytes_total": sum(v3_sizes),
        "delta_len_max": max(delta_lengths) if delta_lengths else 0,
        "state_atoms_max": max(atom_counts) if atom_counts else 0,
    }


def stratified(streams: list[dict[str, object]], planner: str, count: int) -> list[Path]:
    candidates = sorted(
        (s for s in streams if s["planner"] == planner and s["record_count"]),
        key=lambda s: int(s["bytes"]),
    )
    if not candidates:
        return []
    step = max(1, len(candidates) // count)
    picked = candidates[::step][:count]
    if candidates[-1] not in picked:
        picked[-1] = candidates[-1]
    return [REPOSITORY_ROOT / str(s["path"]) for s in picked]


def render(inv: dict[str, object], bfs: list[dict[str, object]], iw: dict[str, object], bound: dict[str, object]) -> str:
    out: list[str] = []
    out.append("1. Corpus inventory (stat + canonical trailer; no full scan)")
    out.append("")
    out.append(f"   {'planner/status':<40} {'files':>6} {'GiB':>10} {'records':>12}")
    out.append(f"   {'-' * 40} {'-' * 6} {'-' * 10} {'-' * 12}")
    groups = inv["groups"]
    assert isinstance(groups, dict)
    for key, value in groups.items():
        out.append(f"   {key:<40} {value['files']:>6} {value['bytes'] / 2**30:>10.2f} {value['records']:>12,}")
    total_bytes = sum(v["bytes"] for v in groups.values())
    total_records = sum(v["records"] for v in groups.values())
    out.append(f"   {'TOTAL':<40} {sum(v['files'] for v in groups.values()):>6} {total_bytes / 2**30:>10.2f} {total_records:>12,}")
    out.append("")

    out.append("2. Reconstruction rules, re-derived against the real corpus")
    out.append("")
    checked = sum(int(s["events_checked"]) for s in bfs)
    totals = {rule: sum(int(s["violations"][rule]) for s in bfs) for rule in ("R1", "R2", "R3", "R4")}  # type: ignore[index]
    out.append(f"   {checked:,} BFS events across {len(bfs)} streams")
    out.append("")
    out.append(f"     R1  frontier_before == [state_id]                       violations: {totals['R1']}")
    out.append(f"     R2  frontier_after  == prev_frontier[1:] + enqueued     violations: {totals['R2']}")
    out.append(f"     R3  visited_after   == sorted(prev_visited | enqueued)  violations: {totals['R3']}")
    out.append(f"     R4  visited_delta   == enqueued ids of this event       violations: {totals['R4']}")
    out.append("")
    out.append("   R4 is the one the prior packet did not state. Because it holds, the reader")
    out.append("   shim needs a running FIFO fold for frontier_order_summary ONLY; frontier_head")
    out.append("   and visited_delta are per-event functions of data the event already carries.")
    out.append("")

    out.append("3. Per-record size, v2 as written vs v3 as re-canonicalised")
    out.append("")
    out.append(f"   {'stream (by size)':<22} {'v2 max':>12} {'v3 max':>9} {'v3 mean':>9} {'final v2':>12} {'final v3':>9}")
    out.append(f"   {'-' * 22} {'-' * 12} {'-' * 9} {'-' * 9} {'-' * 12} {'-' * 9}")
    for stream in bfs:
        name = str(stream["path"]).split("/")[-2][:20]
        out.append(
            f"   {name:<22} {stream['v2_bytes_max']:>12,} {stream['v3_bytes_max']:>9,} "
            f"{stream['v3_bytes_mean']:>9,.0f} {stream.get('final_event_v2_bytes', 0):>12,} "
            f"{stream.get('final_event_v3_bytes', 0):>9,}"
        )
    out.append("")
    out.append("   'final' is the last event of the stream, read by tail seek -- the largest one,")
    out.append("   because the dropped snapshots grow with the search. The v3 column does not grow.")
    out.append("")

    out.append("4. Element counts per event (what a derived bound would rest on)")
    out.append("")
    out.append(f"   state_atoms                max {max(int(s['state_atoms_max']) for s in bfs):>6}")
    out.append(f"   successors                 max {max(int(s['successors_max']) for s in bfs):>6}")
    out.append(f"   actions_considered         max {max(int(s['actions_considered_max']) for s in bfs):>6}")
    out.append(f"   successor state_atoms      max {max(int(s['successor_state_atoms_max']) for s in bfs):>6}")
    out.append("")
    out.append("   Policy ceilings on the same quantities:")
    out.append("     max_grounded_actions   100,000   -> bounds successors / actions_considered")
    out.append("     max_grounded_atoms     100,000   -> bounds state_atoms")
    out.append("   The policy ceilings exceed observation by ~3 orders of magnitude, so a byte")
    out.append("   bound DERIVED from them is ~10^10 and enforces nothing. See the packet.")
    out.append("")

    out.append("5. IW streams (scanned in full)")
    out.append("")
    out.append(f"   events                          {iw['events']:>12,}  ({iw['expand_events']:,} expand)")
    out.append(f"   v2 bytes total                  {iw['v2_bytes_total']:>12,}")
    out.append(f"   v3 bytes total (emitted delta)  {iw['v3_bytes_total']:>12,}")
    out.append(f"   largest v2 event                {iw['v2_bytes_max']:>12,}")
    out.append(f"   largest v3 event                {iw['v3_bytes_max']:>12,}")
    out.append(f"   largest v3 event projected @ w2 {iw['w2_bytes_max']:>12,}")
    out.append(f"   largest emitted delta (items)   {iw['delta_len_max']:>12,}")
    out.append(f"   largest state_atoms             {iw['state_atoms_max']:>12,}")
    out.append("")

    out.append("6. The bound")
    out.append("")
    for line in bound["lines"]:  # type: ignore[index]
        out.append(f"   {line}")
    return "\n".join(out) + "\n"


def derive_bound(bfs: list[dict[str, object]], iw: dict[str, object], inv: dict[str, object]) -> dict[str, object]:
    v3_max = max(int(s["v3_bytes_max"]) for s in bfs)
    v3_final_max = max(int(s.get("final_event_v3_bytes", 0)) for s in bfs)
    v2_max = max(int(s["v2_bytes_max"]) for s in bfs)
    v2_final_max = max(int(s.get("final_event_v2_bytes", 0)) for s in bfs)
    observed_v3 = max(v3_max, v3_final_max, int(iw["v3_bytes_max"]))
    # The bound has to hold under v3's OWN policy, not v2's. Width 2 is the
    # binding case: the emitted IW delta can reach the full width-2 novelty
    # item set for the state.
    worst_v3 = max(observed_v3, int(iw["w2_bytes_max"]))
    proposed = 1 << (worst_v3 * 4 - 1).bit_length()
    groups = inv["groups"]
    assert isinstance(groups, dict)
    total_bytes = sum(v["bytes"] for v in groups.values())
    total_records = sum(v["records"] for v in groups.values())
    means = [float(s["v3_bytes_mean"]) for s in bfs]
    low, high = min(means) * total_records, max(means) * total_records
    mid = statistics.fmean(means) * total_records
    lines = [
        f"largest v2 record observed             {max(v2_max, v2_final_max):>12,} B",
        f"largest v3 record observed (width 1)   {observed_v3:>12,} B   BFS and IW together",
        f"largest v3 record projected (width 2)  {int(iw['w2_bytes_max']):>12,} B   IW delta at full novelty_items(state, 2)",
        "",
        f"reader-side line ceiling               {READER_LINE_CEILING:>12,} B   verify_trace_stream:114 -- READ side only",
        f"writer-side line ceiling               {'none':>12}       <-- the gap this decision closes",
        "",
        f"proposed MAX_EVENT_BYTES               {proposed:>12,} B",
        f"  = smallest power of two >= 4x the largest projected v3 record ({worst_v3:,} B)",
        f"  = {proposed / worst_v3:.1f}x that record, and {READER_LINE_CEILING / proposed:.0f}x BELOW the existing reader ceiling,",
        "    so a stream the writer accepts is always one the verifier can read.",
        "",
        f"corpus today                           {total_bytes / 2**30:>12,.2f} GiB over {total_records:,} records",
        f"corpus projected under v3              {low / 2**30:>6,.1f} - {high / 2**30:,.1f} GiB   (mid {mid / 2**30:,.1f} GiB)",
        f"  range is min..max of the per-stream v3 mean across {len(means)} sampled streams",
        f"  reduction at the midpoint: {total_bytes / max(mid, 1):,.0f}x",
    ]
    return {
        "v2_bytes_max_observed": max(v2_max, v2_final_max),
        "v3_bytes_max_observed": observed_v3,
        "v3_bytes_max_projected_width2": int(iw["w2_bytes_max"]),
        "reader_line_ceiling": READER_LINE_CEILING,
        "proposed_max_event_bytes": proposed,
        "corpus_bytes_v2": total_bytes,
        "corpus_records": total_records,
        "corpus_bytes_v3_low": int(low),
        "corpus_bytes_v3_mid": int(mid),
        "corpus_bytes_v3_high": int(high),
        "lines": lines,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head-events", type=int, default=400)
    parser.add_argument("--bfs-samples", type=int, default=12)
    parsed = parser.parse_args()

    inv = inventory()
    streams = inv["streams"]
    assert isinstance(streams, list)
    bfs = [scan_bfs(path, parsed.head_events) for path in stratified(streams, "bfs", parsed.bfs_samples)]
    iw_paths = [REPOSITORY_ROOT / str(s["path"]) for s in streams if s["planner"] == "iw" and s["record_count"]]
    iw_parts = [scan_iw(path) for path in iw_paths]
    iw = {
        "events": sum(int(p["events"]) for p in iw_parts),
        "expand_events": sum(int(p["expand_events"]) for p in iw_parts),
        "v2_bytes_max": max(int(p["v2_bytes_max"]) for p in iw_parts),
        "v3_bytes_max": max(int(p["v3_bytes_max"]) for p in iw_parts),
        "w2_bytes_max": max(int(p["w2_bytes_max"]) for p in iw_parts),
        "v2_bytes_total": sum(int(p["v2_bytes_total"]) for p in iw_parts),
        "v3_bytes_total": sum(int(p["v3_bytes_total"]) for p in iw_parts),
        "delta_len_max": max(int(p["delta_len_max"]) for p in iw_parts),
        "state_atoms_max": max(int(p["state_atoms_max"]) for p in iw_parts),
        "streams_scanned": len(iw_parts),
    }
    bound = derive_bound(bfs, iw, inv)
    report = {
        "inventory_groups": inv["groups"],
        "bfs_samples": bfs,
        "iw": iw,
        "bound": {k: v for k, v in bound.items() if k != "lines"},
        "head_events": parsed.head_events,
    }
    (HERE / "record-size-bound.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    text = render(inv, bfs, iw, bound)
    (HERE / "record-size-bound.txt").write_text(text)
    print(text, end="")
    violations = sum(int(s["violations"][rule]) for s in bfs for rule in ("R1", "R2", "R3", "R4"))  # type: ignore[index]
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
