#!/usr/bin/env python
"""Measure how much of the trace-v2 corpus is contract-ineligible, and why.

READ-ONLY. Opens every stream for reading only, seeks to the tail, and parses the
trailer record. Creates no checkpoint, cursor, selector result, or trace artifact.
Writes only its own two report files beside this script.

Run:
    source ~/cd_vlaplan
    python .claude/evidence/production-p0-corpus-experiment-readiness/task-4/owner-decision-packet/measure_corpus_eligibility.py

Why the tail read is sound: write_trace_stream (scripts/phase3/cgas_trace_stream_v2.py:76-89)
appends exactly one canonical-JSON `record_type: "trailer"` line as the final line of the
stream, carrying completion_status, record_count, and stream_sha256. verify_trace_stream
rejects any stream whose trailer is not final. So the last line is the authoritative
completion status without reading 2.25 TB of events.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
TRACES = REPO / "tmp/cgas-p0-characterized/traces"
PLANNERS = ("bfs", "iw")
TAIL_WINDOW = 1 << 16


def read_trailer(path: Path) -> dict[str, object]:
    """Return the parsed final record of a trace stream via a bounded tail read."""
    size = path.stat().st_size
    window = TAIL_WINDOW
    while True:
        with path.open("rb") as handle:
            offset = max(0, size - window)
            handle.seek(offset)
            chunk = handle.read()
        lines = [line for line in chunk.split(b"\n") if line]
        if lines and (offset == 0 or chunk.startswith(b"{") or len(lines) > 1):
            return json.loads(lines[-1])
        window *= 4
        if window > (1 << 26):
            raise RuntimeError(f"no trailer found in tail of {path}")


def main() -> None:
    directories = sorted(entry for entry in TRACES.iterdir() if entry.is_dir())
    per_planner: dict[str, dict[str, dict[str, int]]] = {
        planner: defaultdict(lambda: {"files": 0, "bytes": 0, "records": 0}) for planner in PLANNERS
    }
    largest: dict[str, tuple[int, str, str]] = {}
    mismatched_trailers = 0

    for directory in directories:
        for planner in PLANNERS:
            path = directory / f"{planner}.trace-v2.jsonl"
            if not path.is_file():
                continue
            size = path.stat().st_size
            trailer = read_trailer(path)
            if trailer.get("record_type") != "trailer" or trailer.get("planner") != planner:
                mismatched_trailers += 1
                continue
            status = str(trailer.get("completion_status"))
            bucket = per_planner[planner][status]
            bucket["files"] += 1
            bucket["bytes"] += size
            bucket["records"] += int(trailer.get("record_count") or 0)
            if size > largest.get(planner, (0, "", ""))[0]:
                largest[planner] = (size, status, str(path.relative_to(REPO)))

    report: dict[str, object] = {
        "trace_root": str(TRACES.relative_to(REPO)),
        "trace_directories": len(directories),
        "mismatched_trailers": mismatched_trailers,
        "by_planner": {},
        "largest_stream": {planner: {"bytes": value[0], "completion_status": value[1], "path": value[2]} for planner, value in sorted(largest.items())},
    }

    lines: list[str] = []
    lines.append("# Trace-v2 corpus eligibility - READ-ONLY measurement")
    lines.append(f"# trace root: {TRACES.relative_to(REPO)}")
    lines.append(f"# trace directories: {len(directories)}")
    lines.append("")

    for planner in PLANNERS:
        buckets = per_planner[planner]
        total_files = sum(bucket["files"] for bucket in buckets.values())
        total_bytes = sum(bucket["bytes"] for bucket in buckets.values())
        total_records = sum(bucket["records"] for bucket in buckets.values())
        lines.append(f"== {planner.upper()} streams by completion_status ==")
        lines.append(f"  {'status':<26}{'files':>7}{'GB':>12}{'mean':>12}{'records':>14}{'share':>9}")
        planner_report: dict[str, object] = {"total_files": total_files, "total_bytes": total_bytes, "total_records": total_records, "statuses": {}}
        for status, bucket in sorted(buckets.items(), key=lambda item: -item[1]["bytes"]):
            share = bucket["files"] / total_files if total_files else 0.0
            mean = bucket["bytes"] / bucket["files"] if bucket["files"] else 0.0
            lines.append(
                f"  {status:<26}{bucket['files']:>7}{bucket['bytes'] / 2**30:>12.2f}"
                f"{mean / 2**20:>11.1f}M{bucket['records']:>14,}{share:>8.1%}"
            )
            planner_report["statuses"][status] = {  # type: ignore[index]
                "files": bucket["files"],
                "bytes": bucket["bytes"],
                "records": bucket["records"],
                "file_share": round(share, 6),
                "mean_bytes": round(mean, 1),
            }
        lines.append(f"  {'TOTAL':<26}{total_files:>7}{total_bytes / 2**30:>12.2f}{'':>12}{total_records:>14,}")
        lines.append("")
        report["by_planner"][planner] = planner_report  # type: ignore[index]

    # Contract consequence: only eligible_complete_trace can reach a corpus row.
    bfs_statuses = report["by_planner"]["bfs"]["statuses"]  # type: ignore[index]
    ineligible_bytes = sum(value["bytes"] for status, value in bfs_statuses.items() if status != "success_full_trace")
    ineligible_files = sum(value["files"] for status, value in bfs_statuses.items() if status != "success_full_trace")
    total_bfs_bytes = report["by_planner"]["bfs"]["total_bytes"]  # type: ignore[index]
    report["contract_ineligible_bfs"] = {
        "files": ineligible_files,
        "bytes": ineligible_bytes,
        "byte_share": round(ineligible_bytes / total_bfs_bytes, 6) if total_bfs_bytes else 0.0,
        "contract": "scripts/phase3/cgas_partition_contracts.py:45-56 require_full_trace_source accepts only eligible_complete_trace",
    }

    iw_statuses = report["by_planner"]["iw"]["statuses"]  # type: ignore[index]
    iw_success = iw_statuses.get("success_full_trace", {"files": 0})["files"]
    iw_total = report["by_planner"]["iw"]["total_files"]  # type: ignore[index]
    report["iw_success_rate"] = {"success_files": iw_success, "total_files": iw_total, "rate": round(iw_success / iw_total, 6) if iw_total else 0.0}

    lines.append("== Contract consequence ==")
    lines.append(f"  BFS streams that can never yield a corpus row: {ineligible_files} files, {ineligible_bytes / 2**30:.2f} GB")
    lines.append(f"  ({ineligible_bytes / total_bfs_bytes:.1%} of all BFS trace bytes)")
    lines.append("  require_full_trace_source (cgas_partition_contracts.py:45-56) accepts only eligible_complete_trace.")
    lines.append("")
    lines.append("== IW width-1 solvability (the true yield ceiling) ==")
    lines.append(f"  IW success_full_trace: {iw_success} / {iw_total} = {iw_success / iw_total:.1%}")
    lines.append("  Paired-exact needs BOTH planners exact, so this caps yield regardless of ranks consumed.")
    lines.append("")
    lines.append("== Largest stream per planner ==")
    for planner, (size, status, path) in sorted(largest.items()):
        lines.append(f"  {planner}: {size / 2**30:.2f} GB  status={status}  {path}")

    text = "\n".join(lines) + "\n"
    (HERE / "corpus-eligibility.txt").write_text(text, encoding="utf-8")
    (HERE / "corpus-eligibility.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
