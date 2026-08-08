#!/usr/bin/env python
"""Audit the contract surface that trace contract v3 would move.

Read-only. Writes only to this directory. Touches no corpus artifact.

Three questions, all of which the v3 decision packet asserts answers to:

  A. Who reads the five fields v3 removes?
       BFS: frontier_before, frontier_after, visited_after
       IW:  novelty_table_before, novelty_table_after

     The prior packet claimed "cgas_certificate_contracts.py is the only
     consumer of a full snapshot". That claim is load-bearing for the reader
     shim, so this script re-derives it rather than inheriting it.

     Method: census every textual occurrence of the five field names across
     the repository, then match the census against a REVIEWED classification
     table below. If the census and the table disagree in either direction --
     an unclassified hit, or a classified line that no longer exists -- the
     script FAILS. A stale audit is worse than no audit.

  B. Which contract digests move under v3, and therefore what must be
     re-approved? cgas_trace_contract_v2 pins three digests:
       NEW_CONTRACT_SHA256  - stream framing only
       POLICY_SHA256        - the planner limits the streams were produced under
       packet_sha256        - the whole migration packet
     Dropping event-body fields and turning on width escalation do not move
     the same set. This computes which.

  C. Does the record-count bound still hold under width escalation? The IW
     bound formula assumes one search pass. Escalation runs up to max_width
     passes into one stream.

Usage:
    source ~/cd_vlaplan
    python .claude/evidence/cgas-trace-contract-v3/owner-decision-packet/audit_v3_contract_surface.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.phase3.cgas_trace_contract_v2 import (  # noqa: E402
    BFS_MAX_RECORDS,
    IW_MAX_RECORDS,
    NEW_CONTRACT_SHA256,
    POLICY_LIMITS,
    POLICY_SHA256,
    build_migration_packet,
)

BFS_SNAPSHOT_FIELDS = ("frontier_before", "frontier_after", "visited_after")
IW_SNAPSHOT_FIELDS = ("novelty_table_before", "novelty_table_after")
AUDITED_FIELDS = BFS_SNAPSHOT_FIELDS + IW_SNAPSHOT_FIELDS

# Directories that are repository source. Corpus data, rendered frames, caches,
# scratch trees, and this packet's own text are excluded -- they are outputs, not
# consumers, and including them would drown the census in self-reference.
SOURCE_ROOTS = ("scripts", "tests", "examples")

# ---------------------------------------------------------------------------
# The reviewed classification. One entry per (path, line) that mentions any
# audited field inside SOURCE_ROOTS.
#
# lineage:
#   cgas-production  scripts/phase3 code on the CGAS trace path
#   cgas-test        tests/phase3 tests that pin CGAS trace shape
#   slice            examples/planning_benchmark_slice and its tests. A SEPARATE
#                    emitter and schema with its own frontier/visited fields. It
#                    does not read CGAS streams and v3 does not touch it.
#
# role:
#   emitter          writes the field
#   reads-value      consumes the field's contents  <-- the shim must serve these
#   requires-key     validator that fails if the key is absent
#   asserts          test assertion on the field
#   defines-name     a constant/schema listing the name, no read of a stream
# ---------------------------------------------------------------------------
CLASSIFICATION: tuple[tuple[str, int, str, str, str], ...] = (
    # --- CGAS certificate builder: legacy-v1 compatibility only ------------
    ("scripts/phase3/cgas_certificate_contracts.py", 57, "cgas-production", "reads-value", "legacy v1 novelty_table_before -> seen_feature_delta"),
    ("scripts/phase3/cgas_certificate_contracts.py", 58, "cgas-production", "reads-value", "legacy v1 novelty_table_after -> seen_feature_delta"),
    # --- CGAS tests pin that regenerated v3 events omit both snapshots ------
    ("tests/phase3/test_cgas_planner_semantic_parity.py", 184, "cgas-test", "asserts", "width-1 expand omits novelty_table_before"),
    ("tests/phase3/test_cgas_planner_semantic_parity.py", 185, "cgas-test", "asserts", "width-1 expand omits novelty_table_after"),
    ("tests/phase3/test_cgas_planner_semantic_parity.py", 204, "cgas-test", "asserts", "expand and prune events omit novelty_table_before"),
    ("tests/phase3/test_cgas_planner_semantic_parity.py", 205, "cgas-test", "asserts", "expand and prune events omit novelty_table_after"),
    ("tests/phase3/test_cgas_provenance.py", 77, "cgas-test", "asserts", "local width-1 events omit both snapshots"),
    ("tests/phase3/test_cgas_provenance.py", 120, "cgas-test", "asserts", "published width-1 events omit both snapshots"),
    # --- v3 contract surface (added 2026-08-07): names the removed fields so the
    #      drop is a signed, auditable contract property instead of an accident ---
    ("scripts/phase3/cgas_trace_contract_v3.py", 69, "cgas-production", "defines-name", "v3 contract: the BFS fields v3 removes"),
    ("scripts/phase3/cgas_trace_contract_v3.py", 70, "cgas-production", "defines-name", "v3 contract: the IW fields v3 removes"),
    ("scripts/phase3/cgas_trace_contract_v3.py", 78, "cgas-production", "defines-name", "v3 contract: reconstruction rule R1"),
    ("scripts/phase3/cgas_trace_contract_v3.py", 79, "cgas-production", "defines-name", "v3 contract: reconstruction rule R2"),
    ("scripts/phase3/cgas_trace_contract_v3.py", 80, "cgas-production", "defines-name", "v3 contract: reconstruction rule R3"),
    # --- trace-v1 traversal validator: legacy-v1 compatibility only --------
    ("scripts/phase3/trace_contracts.py", 214, "cgas-production", "requires-key", "legacy v1 IW expand events require both novelty snapshots"),
    ("scripts/phase3/trace_contracts.py", 240, "cgas-production", "requires-key", "legacy v1 novelty_table_before must be a list"),
    ("scripts/phase3/trace_contracts.py", 241, "cgas-production", "requires-key", "legacy v1 novelty_table_after must be a list"),
    # --- CGAS tests that pin the raw fields -------------------------------
    ("tests/phase3/test_cgas_bfs_reader_shim.py", 11, "cgas-test", "asserts", "Gate 0b strips all three BFS snapshots before rebuilding fixture certificates"),
    ("tests/phase3/test_cgas_provenance.py", 112, "cgas-test", "asserts", "frontier_before is absent from regenerated traces"),
    ("tests/phase3/test_cgas_planner_semantic_parity.py", 102, "cgas-test", "asserts", "frontier_after is absent from native BFS traces"),
    # --- the separate benchmark slice: not the CGAS lineage ---------------
    ("examples/planning_benchmark_slice/experts/bfs.py", 84, "slice", "emitter", "slice BFS emitter"),
    ("examples/planning_benchmark_slice/experts/bfs.py", 88, "slice", "emitter", "slice BFS emitter"),
    ("examples/planning_benchmark_slice/experts/bfs.py", 93, "slice", "emitter", "slice BFS emitter"),
    ("examples/planning_benchmark_slice/experts/bfs.py", 96, "slice", "emitter", "slice BFS emitter"),
    ("examples/planning_benchmark_slice/experts/bfs.py", 113, "slice", "emitter", "slice BFS emitter"),
    ("examples/planning_benchmark_slice/experts/bfs.py", 114, "slice", "emitter", "slice BFS emitter"),
    ("examples/planning_benchmark_slice/experts/bfs.py", 118, "slice", "emitter", "slice BFS emitter"),
    ("examples/planning_benchmark_slice/experts/iterated_width.py", 138, "slice", "emitter", "slice IW emitter (local variable)"),
    ("examples/planning_benchmark_slice/experts/iterated_width.py", 140, "slice", "emitter", "slice IW emitter (local variable)"),
    ("examples/planning_benchmark_slice/experts/iterated_width.py", 142, "slice", "emitter", "slice IW emitter (local variable)"),
    ("examples/planning_benchmark_slice/experts/iterated_width.py", 144, "slice", "emitter", "slice IW emitter (local variable)"),
    ("examples/planning_benchmark_slice/experts/iterated_width.py", 147, "slice", "emitter", "slice IW emitter (local variable)"),
    ("examples/planning_benchmark_slice/experts/iterated_width.py", 151, "slice", "emitter", "slice IW emitter (local variable)"),
    ("examples/planning_benchmark_slice/experts/iterated_width.py", 154, "slice", "emitter", "slice IW emitter (local variable)"),
    ("examples/planning_benchmark_slice/experts/iterated_width.py", 176, "slice", "emitter", "slice IW emitter"),
    ("examples/planning_benchmark_slice/experts/iterated_width.py", 178, "slice", "emitter", "slice IW emitter"),
    ("examples/planning_benchmark_slice/experts/iterated_width.py", 179, "slice", "emitter", "slice IW emitter"),
    ("examples/planning_benchmark_slice/trajectory_schema.py", 31, "slice", "defines-name", "slice schema field list"),
    ("examples/planning_benchmark_slice/trajectory_schema.py", 32, "slice", "defines-name", "slice schema field list"),
    ("examples/planning_benchmark_slice/trajectory_schema.py", 34, "slice", "defines-name", "slice schema field list"),
    ("examples/planning_benchmark_slice/trajectory_schema.py", 47, "slice", "defines-name", "slice schema field list"),
    ("examples/planning_benchmark_slice/trajectory_schema.py", 48, "slice", "defines-name", "slice schema field list"),
    ("examples/planning_benchmark_slice/trajectory_schema.py", 303, "slice", "reads-value", "slice canonicalization"),
    ("examples/planning_benchmark_slice/trajectory_schema.py", 319, "slice", "requires-key", "slice validator"),
    ("examples/planning_benchmark_slice/trajectory_schema.py", 320, "slice", "requires-key", "slice validator"),
    ("examples/planning_benchmark_slice/trajectory_schema.py", 428, "slice", "reads-value", "slice canonicalization"),
    ("examples/planning_benchmark_slice/trajectory_schema.py", 450, "slice", "reads-value", "slice canonicalization"),
    ("examples/planning_benchmark_slice/modality_serializers.py", 330, "slice", "reads-value", "slice prose serializer"),
    ("tests/planning_benchmark/test_experts_bfs_iw.py", 67, "slice", "asserts", "asserts R1 on the SLICE emitter"),
    ("tests/planning_benchmark/test_experts_bfs_iw.py", 68, "slice", "asserts", "asserts R2 on the SLICE emitter"),
    ("tests/planning_benchmark/test_experts_bfs_iw.py", 70, "slice", "asserts", "asserts sortedness on the SLICE emitter"),
    ("tests/planning_benchmark/test_experts_bfs_iw.py", 84, "slice", "asserts", "slice IW novelty snapshot"),
    ("tests/planning_benchmark/test_experts_bfs_iw.py", 86, "slice", "asserts", "slice IW novelty snapshot"),
    ("tests/planning_benchmark/test_modality_serializers.py", 143, "slice", "asserts", "slice serializer field set"),
    ("tests/planning_benchmark/test_modality_serializers.py", 149, "slice", "asserts", "slice serializer field set"),
    ("tests/planning_benchmark/test_trajectory_schema.py", 71, "slice", "asserts", "slice schema"),
    ("tests/planning_benchmark/test_trajectory_schema.py", 73, "slice", "asserts", "slice schema"),
    ("tests/planning_benchmark/test_trajectory_schema.py", 116, "slice", "asserts", "slice schema"),
    ("tests/planning_benchmark/test_trajectory_schema.py", 117, "slice", "asserts", "slice schema"),
    ("tests/planning_benchmark/test_trajectory_schema.py", 119, "slice", "asserts", "slice schema"),
    ("tests/planning_benchmark/test_trajectory_schema.py", 130, "slice", "asserts", "slice schema"),
    ("tests/planning_benchmark/test_trajectory_schema.py", 131, "slice", "asserts", "slice schema"),
    ("tests/planning_benchmark/test_trajectory_schema.py", 133, "slice", "asserts", "slice schema"),
)

# The v3 policy this packet asks the owner to authorize. Differences from
# POLICY_LIMITS are exactly the width-escalation change plus the expansion-cap
# margin; nothing else moves.
V3_POLICY_LIMITS: dict[str, object] = {
    "local_iw_escalate": 1,
    "local_iw_max_width": 2,
    "local_iw_novelty_max_expansions": 50_000,
    "local_iw_recovery": "disabled",
    "local_iw_width": 1,
    "local_max_applicable_actions": 2_000,
    "max_expansions": 10_000,
    "max_grounded_actions": 100_000,
    "max_grounded_atoms": 100_000,
    "max_plan_length": 128,
}


def census() -> dict[tuple[str, int], str]:
    """Every (path, line) in SOURCE_ROOTS mentioning an audited field name."""
    pattern = r"\|".join(AUDITED_FIELDS)
    completed = subprocess.run(
        ["grep", "-rn", "--include=*.py", "-E", pattern.replace(r"\|", "|"), *SOURCE_ROOTS],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in (0, 1):
        raise SystemExit(f"grep failed: {completed.stderr}")
    hits: dict[tuple[str, int], str] = {}
    for raw in completed.stdout.splitlines():
        path, _, rest = raw.partition(":")
        number, _, text = rest.partition(":")
        hits[(path, int(number))] = text.strip()
    return hits


def reconcile(hits: dict[tuple[str, int], str]) -> dict[str, object]:
    classified = {(path, line): (lineage, role, note) for path, line, lineage, role, note in CLASSIFICATION}
    unclassified = sorted(set(hits) - set(classified))
    vanished = sorted(set(classified) - set(hits))
    rows = [
        {
            "path": path,
            "line": line,
            "lineage": classified[(path, line)][0],
            "role": classified[(path, line)][1],
            "note": classified[(path, line)][2],
            "source": hits[(path, line)],
        }
        for path, line in sorted(set(hits) & set(classified))
    ]
    return {
        "hit_count": len(hits),
        "classified_count": len(classified),
        "unclassified": [{"path": p, "line": n, "source": hits[(p, n)]} for p, n in unclassified],
        "vanished": [{"path": p, "line": n} for p, n in vanished],
        "rows": rows,
    }


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def digest_impact() -> dict[str, object]:
    v2_packet = build_migration_packet()
    # Two different digests share the name "packet_sha256". The field INSIDE the
    # packet is sha256 over the payload with that key removed. The one the owner
    # approval binds to is sha256 over the published packet BYTES (canonical
    # JSON + LF). Report the one the approval checks.
    v2_packet_bytes = json.dumps(
        v2_packet, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode() + b"\n"
    approval = json.loads(
        (REPOSITORY_ROOT / ".claude/evidence/cgas-production-p0/approved-trace-v2.json").read_text()
    )
    changed = sorted(
        key
        for key in set(POLICY_LIMITS) | set(V3_POLICY_LIMITS)
        if POLICY_LIMITS.get(key) != V3_POLICY_LIMITS.get(key)
    )
    return {
        "new_contract_sha256_v2": NEW_CONTRACT_SHA256,
        "new_contract_sha256_v3": NEW_CONTRACT_SHA256,
        "new_contract_moves": False,
        "policy_sha256_v2": POLICY_SHA256,
        "policy_sha256_v3": _digest(V3_POLICY_LIMITS),
        "policy_moves": _digest(V3_POLICY_LIMITS) != POLICY_SHA256,
        "packet_sha256_v2": hashlib.sha256(v2_packet_bytes).hexdigest(),
        "packet_sha256_in_approval": approval["packet_sha256"],
        "packet_digest_reproduces": hashlib.sha256(v2_packet_bytes).hexdigest() == approval["packet_sha256"],
        "policy_sha256_in_approval": approval["policy_sha256"],
        "contract_sha256_in_approval": approval["contract_sha256"],
        "policy_keys_changed": changed,
        "policy_v2": dict(POLICY_LIMITS),
        "policy_v3": dict(V3_POLICY_LIMITS),
    }


def record_bound_impact() -> dict[str, object]:
    probe = json.loads((REPOSITORY_ROOT / ".claude/evidence/phase-a-planner-configuration-probe/result/probe.json").read_text())
    # Total work under escalation is the sum across every width attempted, not
    # only the solving pass -- the failed lower-width passes are real expansions
    # and they land in the same stream.
    totals = [sum(row["escalated"]["expansion_count_by_width"] or [row["escalated"]["expansion_count"]]) for row in probe["results"]]
    per_width = [n for row in probe["results"] for n in (row["escalated"]["expansion_count_by_width"] or [row["escalated"]["expansion_count"]])]
    v2_cap = POLICY_LIMITS["local_iw_novelty_max_expansions"]
    v3_cap = V3_POLICY_LIMITS["local_iw_novelty_max_expansions"]
    actions = V3_POLICY_LIMITS["local_max_applicable_actions"]
    widths = V3_POLICY_LIMITS["local_iw_max_width"] - V3_POLICY_LIMITS["local_iw_width"] + 1
    return {
        "bfs_max_records_v2": BFS_MAX_RECORDS,
        "bfs_max_records_v3": BFS_MAX_RECORDS,
        "iw_max_records_v2": IW_MAX_RECORDS,
        "iw_formula_v2": "1 + 2 * local_iw_novelty_max_expansions * local_max_applicable_actions + 2",
        "iw_formula_v3": "1 + 2 * widths * local_iw_novelty_max_expansions * local_max_applicable_actions + 2",
        "iw_max_records_v3": 1 + 2 * widths * v3_cap * actions + 2,
        "iw_max_records_v3_at_v2_cap": 1 + 2 * widths * v2_cap * actions + 2,
        "widths_under_escalation": widths,
        "candidates": len(totals),
        "observed_max_total_expansions": max(totals),
        "observed_max_single_width_expansions": max(per_width),
        "observed_mean_total_expansions": round(sum(totals) / len(totals), 1),
        "v2_cap": v2_cap,
        "v2_margin_over_observed_max": round(v2_cap / max(per_width), 2),
        "v3_cap": v3_cap,
        "v3_margin_over_observed_max": round(v3_cap / max(per_width), 2),
    }


def render(audit: dict[str, object], digests: dict[str, object], bounds: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append("A. Consumers of the five fields trace contract v3 removes")
    lines.append("")
    lines.append(f"   {audit['hit_count']} occurrences in {', '.join(SOURCE_ROOTS)}; "
                 f"{audit['classified_count']} classified; "
                 f"{len(audit['unclassified'])} unclassified; {len(audit['vanished'])} stale.")
    lines.append("")
    rows = audit["rows"]
    assert isinstance(rows, list)
    by_bucket: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        by_bucket.setdefault((str(row["lineage"]), str(row["role"])), []).append(row)
    lines.append(f"   {'lineage':<16} {'role':<14} {'n':>3}")
    lines.append(f"   {'-' * 16} {'-' * 14} {'-' * 3}")
    for (lineage, role), bucket in sorted(by_bucket.items()):
        lines.append(f"   {lineage:<16} {role:<14} {len(bucket):>3}")
    lines.append("")
    lines.append("   Every line that CONSUMES a value (reads-value / requires-key) on the CGAS path:")
    lines.append("")
    for row in rows:
        if row["lineage"] == "cgas-production" and row["role"] in {"reads-value", "requires-key"}:
            lines.append(f"     {row['path']}:{row['line']}  [{row['role']}]")
            lines.append(f"       {row['note']}")
    lines.append("")
    if audit["unclassified"]:
        lines.append("   *** UNCLASSIFIED HITS -- the audit is stale, do not trust the table above ***")
        for item in audit["unclassified"]:  # type: ignore[union-attr]
            lines.append(f"     {item['path']}:{item['line']}  {item['source']}")
        lines.append("")
    if audit["vanished"]:
        lines.append("   *** CLASSIFIED LINES THAT NO LONGER EXIST -- re-review before citing ***")
        for item in audit["vanished"]:  # type: ignore[union-attr]
            lines.append(f"     {item['path']}:{item['line']}")
        lines.append("")

    lines.append("B. Which contract digests move under v3")
    lines.append("")
    lines.append(f"   NEW_CONTRACT_SHA256  {digests['new_contract_sha256_v2'][:16]}...  "
                 f"{'MOVES' if digests['new_contract_moves'] else 'unchanged -- framing only, no event field set'}")
    lines.append(f"   POLICY_SHA256        {digests['policy_sha256_v2'][:16]}...  "
                 f"{'MOVES' if digests['policy_moves'] else 'unchanged'}")
    lines.append(f"                     -> {digests['policy_sha256_v3'][:16]}...")
    lines.append(f"   packet_sha256        {digests['packet_sha256_v2'][:16]}...  MOVES (it embeds policy_sha256)")
    lines.append(f"                        reproduces the digest in approved-trace-v2.json: {digests['packet_digest_reproduces']}")
    lines.append("")
    lines.append("   Policy keys that differ:")
    for key in digests["policy_keys_changed"]:  # type: ignore[union-attr]
        before = digests["policy_v2"].get(key, "<absent>")  # type: ignore[union-attr]
        after = digests["policy_v3"].get(key, "<absent>")  # type: ignore[union-attr]
        lines.append(f"     {key:<36} {before!r} -> {after!r}")
    lines.append("")

    lines.append("C. Record-count bound under width escalation")
    lines.append("")
    lines.append(f"   BFS  {bounds['bfs_max_records_v2']:>15,}  unchanged")
    lines.append(f"   IW   {bounds['iw_max_records_v2']:>15,}  v2, formula: {bounds['iw_formula_v2']}")
    lines.append(f"        {bounds['iw_max_records_v3_at_v2_cap']:>15,}  v3 at the UNCHANGED cap -- escalation alone doubles it")
    lines.append(f"        {bounds['iw_max_records_v3']:>15,}  v3 at the proposed cap, formula: {bounds['iw_formula_v3']}")
    lines.append(f"        widths under escalation = {bounds['widths_under_escalation']}")
    lines.append("")
    lines.append(f"   Expansion cap against what Phase A observed over {bounds['candidates']} candidates:")
    lines.append(f"     largest total expansions (summed across widths)      {bounds['observed_max_total_expansions']:>8,}")
    lines.append(f"     largest single-width pass                            {bounds['observed_max_single_width_expansions']:>8,}")
    lines.append(f"     mean total expansions                                {bounds['observed_mean_total_expansions']:>8}")
    lines.append(f"     v2 cap {bounds['v2_cap']:,} -> margin {bounds['v2_margin_over_observed_max']}x over the largest single pass")
    lines.append(f"     v3 cap {bounds['v3_cap']:,} -> margin {bounds['v3_margin_over_observed_max']}x over the largest single pass")
    lines.append("")
    lines.append("   NOTE the cap is applied PER WIDTH PASS (local_iw.py:99 resets `expansions`")
    lines.append("   for each pass), so the single-pass column is the one it binds against.")
    return "\n".join(lines) + "\n"


def novelty_truncation() -> dict[str, object]:
    """How badly the 200-entry trace clip understates the width-2 novelty table.

    The clip is `sorted(...)[:MAX_IW_TRACE_NOVELTY_ITEMS]` in
    local_iw_novelty.serialized_novelty_table, so a trace-visible 200 means
    ">=200, true value unknown". The probe reconstructed true cardinality from
    the events themselves; this reports it per object count.
    """
    from scripts.phase3.local_iw_novelty import MAX_IW_TRACE_NOVELTY_ITEMS  # noqa: PLC0415

    probe = json.loads((REPOSITORY_ROOT / ".claude/evidence/phase-a-planner-configuration-probe/result/probe.json").read_text())
    instrumented = [
        row
        for row in probe["results"]
        if isinstance(row.get("peak_novelty_table"), dict) and row["peak_novelty_table"].get("true_peak") is not None
    ]
    per_count: dict[int, dict[str, object]] = {}
    for row in instrumented:
        bucket = per_count.setdefault(
            int(row["object_count"]), {"n": 0, "true_peak": 0, "clipped_peak": 0, "saturated": 0, "ratios": []}
        )
        peak = row["peak_novelty_table"]
        bucket["n"] = int(bucket["n"]) + 1
        bucket["true_peak"] = max(int(bucket["true_peak"]), int(peak["true_peak"]))
        bucket["clipped_peak"] = max(int(bucket["clipped_peak"]), int(peak["clipped_peak"]))
        bucket["saturated"] = int(bucket["saturated"]) + (1 if peak["saturated"] else 0)
        bucket["ratios"].append(int(peak["true_peak"]) / max(int(peak["clipped_peak"]), 1))  # type: ignore[union-attr]
    for bucket in per_count.values():
        ratios = bucket.pop("ratios")
        assert isinstance(ratios, list)
        bucket["understatement_max"] = round(max(ratios), 1)
        bucket["understatement_mean"] = round(sum(ratios) / len(ratios), 1)
    return {
        "clip": MAX_IW_TRACE_NOVELTY_ITEMS,
        "instrumented": len(instrumented),
        "by_object_count": {str(k): v for k, v in sorted(per_count.items())},
    }


def main() -> int:
    hits = census()
    audit = reconcile(hits)
    digests = digest_impact()
    bounds = record_bound_impact()
    novelty = novelty_truncation()
    report = {
        "field_consumers": audit,
        "digest_impact": digests,
        "record_bounds": bounds,
        "novelty_truncation": novelty,
    }
    (HERE / "contract-surface.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    text = render(audit, digests, bounds) + render_novelty(novelty)
    (HERE / "contract-surface.txt").write_text(text)
    print(text, end="")
    return 1 if audit["unclassified"] or audit["vanished"] else 0


def render_novelty(novelty: dict[str, object]) -> str:
    lines = ["", "D. IW novelty-table truncation, the defect the emitted delta repairs", ""]
    lines.append(f"   MAX_IW_TRACE_NOVELTY_ITEMS = {novelty['clip']}  (local_iw_novelty.py:8, applied at :30)")
    lines.append(f"   {novelty['instrumented']} instrumented width-2 runs")
    lines.append("")
    lines.append(f"   {'n':>4} {'runs':>5} {'visible peak':>13} {'true peak':>10} {'understated max':>16} {'mean':>6} {'saturated':>10}")
    lines.append(f"   {'-' * 4} {'-' * 5} {'-' * 13} {'-' * 10} {'-' * 16} {'-' * 6} {'-' * 10}")
    for key, bucket in novelty["by_object_count"].items():  # type: ignore[union-attr]
        lines.append(
            f"   {key:>4} {bucket['n']:>5} {bucket['clipped_peak']:>13,} {bucket['true_peak']:>10,} "
            f"{str(bucket['understatement_max']) + 'x':>16} {str(bucket['understatement_mean']) + 'x':>6} "
            f"{str(bucket['saturated']) + '/' + str(bucket['n']):>10}"
        )
    lines.append("")
    lines.append("   'understated' is per instance: true_peak / trace-visible peak, max and mean")
    lines.append("   over the instrumented runs at that object count.")
    lines.append("")
    lines.append("   Under legacy v1, seen_feature_delta was reconstructed from two CLIPPED snapshots")
    lines.append("   (cgas_certificate_contracts.py:57-58), so at width 2 it was unsound by the")
    lines.append("   understatement factor above. The v3 emitter removes the clip from the")
    lines.append("   correctness path entirely -- the delta is bounded by novelty_items(state, 2),")
    lines.append("   which is |atoms| + C(|atoms|, 2) and does not grow with the search.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
