#!/usr/bin/env python
"""Derive the pilot-corpus scope numbers behind decisions 2 and 3.

Read-only. Reads the round-1 checkpoint and the Phase A probe result. Writes
only to this directory. Runs no planner, opens no trace stream, advances no
cursor.

  Decision 2 -- off-plan expansion certificates.
    Training transitions currently come from the replayed plan, so steps per
    instance == plan length. BFS expands far more states than the plan visits.
    This measures that ratio on the width-2 paired-exact set and prices the
    pilot under both harvesting modes.

  Decision 3 -- does the pilot need release-grade provenance?
    This checks which of Todos 5-10's modules exist, which have tests, and --
    the part the pipeline audit got wrong -- which of their properties are
    already enforced by modules that DO exist.

Also re-derives two Phase A figures the packet cites as sizing input:
the n=4 quota ceiling under width 2, and the width-2 paired-exact set size.

Usage:
    source ~/cd_vlaplan
    python .claude/evidence/cgas-trace-contract-v3/owner-decision-packet/derive_pilot_scope.py
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))

CHECKPOINT = REPOSITORY_ROOT / "tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json"
PROBE = REPOSITORY_ROOT / ".claude/evidence/phase-a-planner-configuration-probe/result/probe.json"

# The first-failure matrix: 7 certificate invariant families from
# cgas_certificate_contracts.BFS_FIELDS + IW_FIELDS, against 3 object counts.
INVARIANT_FAMILIES = 7
OBJECT_COUNTS = 3
CELLS = INVARIANT_FAMILIES * OBJECT_COUNTS
HELD_OUT_FRACTION = (39 + 40) / 481          # dev + test of the 481-row production target
N4_UNIVERSE = 210                            # closed, nontrivial 4-object identities

# Todo -> (module, test) under the production plan's Todos 5-10.
M2_MODULES = (
    (5, "cgas_production_review_packet", "assemble a human review packet", "release-process"),
    (6, "cgas_partition_materialize", "materialize the selected partition", "correctness"),
    (7, "cgas_production_staging", "stage before publication", "release-process"),
    (8, "cgas_certificates_alignment_binding", "bind certificates to aligned renders", "correctness"),
    (10, "cgas_production_release", "atomic release with rollback", "release-process"),
)

# Correctness invariants a pilot must not lose, and where they are enforced TODAY.
EXISTING_GUARDS = (
    ("replay-valid transitions", "scripts/phase3/cgas_alignment.py", "build_alignment rejects unproven replays"),
    ("certificate re-derivation", "scripts/phase3/cgas_certificates.py", "verify_steps rebuilds every certificate from the trace and fails closed"),
    ("no oracle leakage", "scripts/phase3/cgas_certificate_contracts.py", "validate_model_input against ORACLE_FIELDS"),
    ("schema validity", "scripts/phase3/cgas_certificate_contracts.py", "step_schema, validated with Draft202012Validator"),
    ("certificate <-> alignment binding", "tests/phase3/test_cgas_certificates_alignment_binding.py", "12 tests over the EXISTING modules"),
    ("release digest immutability", "scripts/phase3/cgas_release_gate.py", "present and working"),
)


def load() -> tuple[list[dict], list[dict]]:
    checkpoint = json.loads(CHECKPOINT.read_text())
    rows = [json.loads(line) for line in checkpoint["characterization"]["canonical_jsonl"].splitlines()]
    probe = json.loads(PROBE.read_text())["results"]
    return rows, probe


def off_plan(rows: list[dict], probe: list[dict]) -> dict[str, object]:
    by_id = {row["candidate_id"]: row for row in rows}
    paired: list[dict[str, object]] = []
    for entry in probe:
        if not (entry["bfs_exact"] and entry["escalated"]["exact"]):
            continue
        row = by_id.get(entry["candidate_id"])
        if row is None:
            continue
        paired.append(
            {
                "object_count": entry["object_count"],
                "plan_length": entry["escalated"]["plan_length"],
                "bfs_expansions": row["bfs"]["exact_search"]["expansion_count"],
            }
        )
    plans = [int(p["plan_length"]) for p in paired]
    expansions = [int(p["bfs_expansions"]) for p in paired]
    mean_plan = statistics.fmean(plans)
    mean_expansions = statistics.fmean(expansions)
    return {
        "paired_exact_instances_width2": len(paired),
        "mean_plan_length": round(mean_plan, 2),
        "median_plan_length": statistics.median(plans),
        "max_plan_length": max(plans),
        "mean_bfs_expansions": round(mean_expansions, 1),
        "median_bfs_expansions": statistics.median(expansions),
        "off_plan_ratio": round(mean_expansions / mean_plan, 1),
        "steps_per_instance_on_plan": round(2 * mean_plan, 2),   # one BFS + one IW row per plan step
        "steps_per_instance_off_plan": round(2 * mean_expansions, 1),
    }


def sizing(ratio: dict[str, object]) -> list[dict[str, object]]:
    table: list[dict[str, object]] = []
    for harvest, per_instance in (
        ("on-plan (today)", float(ratio["steps_per_instance_on_plan"])),
        ("off-plan expansions", float(ratio["steps_per_instance_off_plan"])),
    ):
        for bar in (10, 30):
            for failure_rate in (0.40, 0.60):
                failures = CELLS * bar
                held_out_steps = failures / failure_rate
                total_steps = held_out_steps / HELD_OUT_FRACTION
                table.append(
                    {
                        "harvest": harvest,
                        "bar": bar,
                        "failure_rate": failure_rate,
                        "failures_needed": failures,
                        "held_out_steps": round(held_out_steps),
                        "total_steps": round(total_steps),
                        "instances": math.ceil(total_steps / per_instance),
                        # Every certificate row needs an aligned pre-state render
                        # (cgas_certificates requires alignment.png_sha256 and
                        # vision_status), so renders track ROWS, not instances --
                        # and rows are two per step, one BFS and one IW, over the
                        # same rendered state.
                        "renders": round(total_steps / 2),
                    }
                )
    return table


def n4_ceiling(probe: list[dict]) -> dict[str, object]:
    n4 = [entry for entry in probe if entry["object_count"] == 4]
    exact_w2 = sum(1 for entry in n4 if entry["escalated"]["exact"])
    exact_w1 = sum(1 for entry in n4 if entry["width_one"]["exact"])
    return {
        "characterized": len(n4),
        "universe": N4_UNIVERSE,
        "exact_width1": exact_w1,
        "exact_width2": exact_w2,
        "rate_width2": round(100 * exact_w2 / len(n4), 1),
        "ceiling_width1": exact_w1 + (N4_UNIVERSE - len(n4)),
        "ceiling_width2": exact_w2 + (N4_UNIVERSE - len(n4)),
        "required": 190,
    }


def m2_audit() -> dict[str, object]:
    modules = []
    for todo, name, purpose, kind in M2_MODULES:
        modules.append(
            {
                "todo": todo,
                "module": name,
                "purpose": purpose,
                "kind": kind,
                "module_present": (REPOSITORY_ROOT / f"scripts/phase3/{name}.py").is_file(),
                "test_present": (REPOSITORY_ROOT / f"tests/phase3/test_{name}.py").is_file(),
            }
        )
    guards = [
        {"invariant": inv, "enforced_in": where, "how": how, "present": (REPOSITORY_ROOT / where).exists()}
        for inv, where, how in EXISTING_GUARDS
    ]
    return {"modules": modules, "existing_guards": guards}


def render(ratio: dict, table: list[dict], ceiling: dict, audit: dict) -> str:
    out: list[str] = []
    out.append("1. Off-plan expansion ratio (width-2 paired-exact set)")
    out.append("")
    out.append(f"   instances                       {ratio['paired_exact_instances_width2']:>8}")
    out.append(f"   mean plan length                {ratio['mean_plan_length']:>8}   median {ratio['median_plan_length']}, max {ratio['max_plan_length']}")
    out.append(f"   mean BFS expansions / instance  {ratio['mean_bfs_expansions']:>8}   median {ratio['median_bfs_expansions']}")
    out.append(f"   off-plan ratio                  {ratio['off_plan_ratio']:>8}x")
    out.append("")
    out.append(f"   certificate rows per instance, on-plan     {ratio['steps_per_instance_on_plan']:>8}")
    out.append(f"   certificate rows per instance, off-plan    {ratio['steps_per_instance_off_plan']:>8}")
    out.append("   (two rows per step -- one BFS certificate, one IW certificate)")
    out.append("")

    out.append("2. Pilot instances needed for a stable first-failure matrix")
    out.append("")
    out.append(f"   {CELLS} cells = {INVARIANT_FAMILIES} invariant families x {OBJECT_COUNTS} object counts;"
               f" held-out fraction {HELD_OUT_FRACTION:.3f}")
    out.append("")
    out.append(f"   {'harvest':<22} {'bar':>5} {'fail%':>6} {'rows':>9} {'renders':>9} {'instances':>10}")
    out.append(f"   {'-' * 22} {'-' * 5} {'-' * 6} {'-' * 9} {'-' * 9} {'-' * 10}")
    for entry in table:
        out.append(
            f"   {entry['harvest']:<22} {'>=' + str(entry['bar']):>5} {entry['failure_rate'] * 100:>5.0f}% "
            f"{entry['total_steps']:>9,} {entry['renders']:>9,} {entry['instances']:>10,}"
        )
    out.append("")
    out.append("   Production target is 481 instances. On-plan at >=30/cell the 'pilot' exceeds it;")
    out.append("   off-plan it is small at every bar.")
    out.append("")
    out.append("   READ THE RENDER COLUMN. It does not move. Off-plan harvesting cuts the number")
    out.append("   of instances to enumerate, plan, and BFS-trace by ~50x; it cuts the render bill")
    out.append("   by nothing, because every certificate row still needs an aligned pre-state PNG.")
    out.append("   The lever is on characterization cost, not on the external render service.")
    out.append("")

    out.append("3. n=4 quota ceiling under width 2 (sizing input for Phase 0c)")
    out.append("")
    out.append(f"   universe closed at              {ceiling['universe']:>6}")
    out.append(f"   characterized in round 1        {ceiling['characterized']:>6}")
    out.append(f"   exact at width 1                {ceiling['exact_width1']:>6}   -> ceiling {ceiling['ceiling_width1']}")
    out.append(f"   exact at width 2                {ceiling['exact_width2']:>6}   ({ceiling['rate_width2']}%) -> ceiling {ceiling['ceiling_width2']}")
    out.append(f"   EXPECTED_OBJECT_COUNTS[4]       {ceiling['required']:>6}   -> still short by "
               f"{ceiling['required'] - ceiling['ceiling_width2']}")
    out.append("")

    out.append("4. Todos 5-10: what exists")
    out.append("")
    out.append(f"   {'todo':>4} {'module':<38} {'kind':<16} {'module':>7} {'test':>6}")
    out.append(f"   {'-' * 4} {'-' * 38} {'-' * 16} {'-' * 7} {'-' * 6}")
    for item in audit["modules"]:
        out.append(
            f"   {item['todo']:>4} {item['module']:<38} {item['kind']:<16} "
            f"{'yes' if item['module_present'] else 'MISSING':>7} {'yes' if item['test_present'] else 'no':>6}"
        )
    out.append("")
    out.append("   Correctness invariants a pilot must not lose, and where they are enforced today:")
    out.append("")
    for guard in audit["existing_guards"]:
        mark = "ok " if guard["present"] else "!! "
        out.append(f"     {mark}{guard['invariant']:<34} {guard['enforced_in']}")
        out.append(f"         {guard['how']}")
    return "\n".join(out) + "\n"


def main() -> int:
    rows, probe = load()
    ratio = off_plan(rows, probe)
    table = sizing(ratio)
    ceiling = n4_ceiling(probe)
    audit = m2_audit()
    report = {"off_plan": ratio, "sizing": table, "n4_ceiling": ceiling, "m2_audit": audit}
    (HERE / "pilot-scope.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    text = render(ratio, table, ceiling, audit)
    (HERE / "pilot-scope.txt").write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
