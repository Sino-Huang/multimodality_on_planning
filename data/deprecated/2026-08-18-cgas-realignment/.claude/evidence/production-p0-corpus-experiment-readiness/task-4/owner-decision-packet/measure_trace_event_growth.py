#!/usr/bin/env python
"""Quantify trace-v2 event growth and test exact reconstructibility of the snapshot fields.

READ-ONLY. Opens streams for reading only; writes only its own two report files
beside this script. Creates no checkpoint, cursor, selector result, or trace artifact.

Run:
    source ~/cd_vlaplan
    python .claude/evidence/production-p0-corpus-experiment-readiness/task-4/owner-decision-packet/measure_trace_event_growth.py

Two questions, answered by measurement rather than assertion:

  Q1 (cost)   How much of a trace-v2 stream is the three snapshot fields
              frontier_before / frontier_after / visited_after?

  Q2 (safety) Are those fields exactly reconstructible from the rest of the event?
              The reconstruction rules are read off the emitter
              (scripts/phase3/cgas_bfs.py:122-137, _StateIndex.expansion):

                R1  frontier_before[i] == [state_id[i]]
                    Line 132 emits `"frontier_before": [state_id]` - a literal
                    restatement of state_id. It carries no information at all.

                R2  frontier_after[i] == frontier_after[i-1][1:] + enqueued(i)
                    Line 131 emits the FIFO deque. Each expansion popleft()s the head
                    (line 41) and appends exactly the successors with enqueued=True
                    (lines 65-74). enqueued(i) is recorded per successor row.

                R3  visited_after[i] == sorted(visited_after[i-1] | enqueued(i))
                    Line 136 emits _StateIndex._visited, maintained by insort
                    (line 120), i.e. a sorted set that only ever gains the ids
                    added at line 73 - the same enqueued successors.

              Base case at i == 0: the deque starts as [start] and is immediately
              popped, so frontier_after[0] == enqueued(0), and _visited starts as
              [state_id[0]] (line 110), so visited_after[0] == sorted({state_id[0]} | enqueued(0)).

If R1-R3 hold on every event, the three fields are pure redundancy: a v2.1 reader can
rebuild them byte-identically from data the stream already carries. Any violation
anywhere means the proposal is unsound and must not ship.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
TRACES = REPO / "tmp/cgas-p0-characterized/traces"

SNAPSHOT_FIELDS = ("frontier_before", "frontier_after", "visited_after")

# One mid-sized success_full_trace stream, scanned end to end.
FULL_SCAN = "245517bf069a45df7c1ff654b25edc3941f43f84ad121e8690e337a7038b2343"
# The largest stream in the corpus (skipped_resource_limit), scanned as a bounded prefix.
PREFIX_SCAN = "0a60381d43e9893ce8a4914e8b3d761a27d576a292a771e134ef99fd0995b3d0"
PREFIX_BYTE_BUDGET = 2 * 2**30

SEPARATORS = (",", ":")


def scan(path: Path, byte_budget: int | None) -> dict[str, object]:
    """Walk a stream's events, measuring snapshot cost and verifying R1-R3 exactly."""
    consumed = 0
    events = 0
    snapshot_bytes = 0
    other_bytes = 0
    first_line_bytes = 0
    last_line_bytes = 0
    first_frontier = 0
    last_frontier = 0
    last_visited = 0
    violations: dict[str, list[int]] = {"R1": [], "R2": [], "R3": []}
    expected_frontier: list[str] | None = None
    expected_visited: list[str] | None = None
    truncated = False

    with path.open("rb") as handle:
        for line in handle:
            if byte_budget is not None and consumed + len(line) > byte_budget:
                truncated = True
                break
            consumed += len(line)
            record = json.loads(line)
            if record.get("record_type") != "event":
                continue
            event = record["event"]
            sequence = int(record["sequence"])

            snapshot = sum(len(json.dumps(event[field], separators=SEPARATORS)) for field in SNAPSHOT_FIELDS if field in event)
            snapshot_bytes += snapshot
            other_bytes += len(line) - snapshot

            state_id = event["state_id"]
            frontier_before = event["frontier_before"]
            frontier_after = event["frontier_after"]
            visited_after = event["visited_after"]
            enqueued = [row["state_id"] for row in event["successors"] if row["enqueued"]]

            # R1 - frontier_before is a restatement of state_id.
            if frontier_before != [state_id]:
                violations["R1"].append(sequence)

            # R2/R3 - rebuild from the predecessor and compare byte-for-byte.
            if expected_frontier is None:
                rebuilt_frontier = list(enqueued)
                rebuilt_visited = sorted({state_id, *enqueued})
            else:
                rebuilt_frontier = expected_frontier[1:] + enqueued
                rebuilt_visited = sorted(set(expected_visited or []) | set(enqueued))
            if frontier_after != rebuilt_frontier:
                violations["R2"].append(sequence)
            if visited_after != rebuilt_visited:
                violations["R3"].append(sequence)

            # Continue from the stream's own values so one violation cannot cascade.
            expected_frontier = frontier_after
            expected_visited = visited_after

            if events == 0:
                first_line_bytes = len(line)
                first_frontier = len(frontier_after)
            last_line_bytes = len(line)
            last_frontier = len(frontier_after)
            last_visited = len(visited_after)
            events += 1

    projected = other_bytes
    total_violations = sum(len(value) for value in violations.values())
    return {
        "path": str(path.relative_to(REPO)),
        "stream_bytes": path.stat().st_size,
        "scanned_bytes": consumed,
        "truncated": truncated,
        "events": events,
        "snapshot_bytes": snapshot_bytes,
        "other_bytes": other_bytes,
        "snapshot_share": round(snapshot_bytes / consumed, 6) if consumed else 0.0,
        "projected_bytes": projected,
        "projected_reduction": round(1 - projected / consumed, 6) if consumed else 0.0,
        "first_event_bytes": first_line_bytes,
        "last_event_bytes": last_line_bytes,
        "first_frontier_len": first_frontier,
        "last_frontier_len": last_frontier,
        "last_visited_len": last_visited,
        "growth_factor": round(last_line_bytes / first_line_bytes, 1) if first_line_bytes else 0.0,
        "violations": {rule: value[:20] for rule, value in violations.items()},
        "violation_counts": {rule: len(value) for rule, value in violations.items()},
        "exactly_reconstructible": total_violations == 0,
    }


def render(label: str, result: dict[str, object]) -> list[str]:
    scanned = int(result["scanned_bytes"])
    counts = result["violation_counts"]
    lines = [
        f"== {label} ==",
        f"  path                 {result['path']}",
        f"  stream size          {int(result['stream_bytes']) / 2**30:.2f} GB",
        f"  scanned              {scanned / 2**30:.2f} GB ({'bounded prefix' if result['truncated'] else 'complete'}), {result['events']:,} events",
        "",
        "  -- Q1: where the bytes go --",
        f"  snapshot fields      {int(result['snapshot_bytes']) / 2**30:.3f} GB  ({float(result['snapshot_share']):.1%} of scanned bytes)",
        f"  everything else      {int(result['other_bytes']) / 2**30:.3f} GB",
        f"  first event          {result['first_event_bytes']:,} bytes  (frontier {result['first_frontier_len']})",
        f"  last event           {result['last_event_bytes']:,} bytes  (frontier {result['last_frontier_len']:,}, visited {result['last_visited_len']:,})",
        f"  growth across run    {result['growth_factor']}x",
        "",
        "  -- Q2: are the snapshots exactly reconstructible? --",
        f"  R1 frontier_before == [state_id]                      violations: {counts['R1']}",  # type: ignore[index]
        f"  R2 frontier_after  == prev[1:] + enqueued             violations: {counts['R2']}",  # type: ignore[index]
        f"  R3 visited_after   == sorted(prev | enqueued)         violations: {counts['R3']}",  # type: ignore[index]
        f"  VERDICT              {'EXACTLY RECONSTRUCTIBLE' if result['exactly_reconstructible'] else 'NOT RECONSTRUCTIBLE - DO NOT SHIP'}",
        "",
        "  -- projected size if the three fields are dropped --",
        f"  projected stream     {int(result['projected_bytes']) / 2**30:.3f} GB",
        f"  reduction            {float(result['projected_reduction']):.2%}",
        "",
    ]
    for rule, sequences in result["violations"].items():  # type: ignore[union-attr]
        if sequences:
            lines.insert(-1, f"  first {rule} violations at sequences: {sequences}")
    return lines


def main() -> None:
    full = scan(TRACES / FULL_SCAN / "bfs.trace-v2.jsonl", None)
    prefix = scan(TRACES / PREFIX_SCAN / "bfs.trace-v2.jsonl", PREFIX_BYTE_BUDGET)

    lines = ["# trace-v2 snapshot cost and reconstructibility - READ-ONLY measurement", ""]
    lines += render("A. mid-sized success_full_trace stream, scanned end to end", full)
    lines += render("B. largest stream in the corpus (skipped_resource_limit), bounded 2 GB prefix", prefix)
    lines += [
        "== Reading ==",
        "  Q1 answers whether the fix is worth doing. Q2 answers whether it is safe.",
        "  EXACTLY RECONSTRUCTIBLE means every snapshot in the scanned region was rebuilt",
        "  byte-identically from data the event already carries, so dropping the fields",
        "  loses no information a reader cannot recover. It does NOT by itself authorize",
        "  the contract change - see DECISION.md item 2.",
        "",
    ]

    text = "\n".join(lines)
    (HERE / "trace-event-growth.txt").write_text(text, encoding="utf-8")
    (HERE / "trace-event-growth.json").write_text(json.dumps({"full_scan": full, "prefix_scan": prefix}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
