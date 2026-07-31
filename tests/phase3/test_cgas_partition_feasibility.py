from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.phase3.cgas_characterization_bundle import parse_bundle
from scripts.phase3.cgas_partition_feasibility import analyze_bundle, analyze_rows


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_PATH = REPOSITORY_ROOT / "tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas"
BUNDLE_SHA256 = "942d7be93ad0eb0ec6580bfe380fb8f09141662140ffc3d3c98e7f09a10ddaf4"


def test_analyze_bundle_reports_actual_blocker_and_indeterminate_downstream_feasibility() -> None:
    # Given: the verified characterization bundle with incomplete 12-object traces.
    bundle = BUNDLE_PATH.read_bytes()

    # When: feasibility is observed without constructing a partition draft.
    report = analyze_bundle(bundle)

    # Then: only the paired-exact blocker is authoritative while successor metrics are unavailable.
    assert report.paired_exact_row_count == 24
    assert report.paired_exact_signature_count == 10
    assert report.paired_exact_object_counts == ((4, 24),)
    assert report.ineligible_row_count == 457
    assert report.downstream_feasibility == "indeterminate_non_exact_metrics"
    assert report.failure_reasons == (
        "structural_ood_ineligible",
        "indeterminate_non_exact_metrics",
    )
    assert "records" not in report.__dataclass_fields__
    assert "roles" not in report.__dataclass_fields__
    assert all(not field.startswith(("optimistic_", "residual_", "calibration_")) for field in report.__dataclass_fields__)


def test_analyze_bundle_is_reverse_input_deterministic_and_preserves_bundle_bytes() -> None:
    # Given: one immutable verified bundle and its parsed characterization rows.
    original = BUNDLE_PATH.read_bytes()
    parsed = parse_bundle(original)
    members = {member.name: member.contents for member in parsed.members}
    rows = tuple(json.loads(line) for line in members["characterization.jsonl"].splitlines())

    # When: the same rows are observed in forward and reverse order.
    forward = analyze_rows(rows)
    reverse = analyze_rows(tuple(reversed(rows)))

    # Then: counts remain identical and observation did not change the bundle.
    assert forward == reverse
    assert hashlib.sha256(BUNDLE_PATH.read_bytes()).hexdigest() == BUNDLE_SHA256
    assert BUNDLE_PATH.read_bytes() == original


def test_analyze_rows_keeps_downstream_feasibility_indeterminate_when_bounded_metrics_change() -> None:
    # Given: verified rows and a copy with arbitrary metric changes on non-paired-exact rows.
    parsed = parse_bundle(BUNDLE_PATH.read_bytes())
    members = {member.name: member.contents for member in parsed.members}
    rows = tuple(json.loads(line) for line in members["characterization.jsonl"].splitlines())
    perturbed = json.loads(json.dumps(rows))
    for row in perturbed:
        if row["object_count"] == 12:
            for planner in (row["bfs"], row["iw_width_1"]):
                planner["exact_search"]["plan_length"] = 1_000_000
                planner["exact_search"]["expansion_count"] = 1_000_000

    # When: both populations are observed through the authoritative feasibility boundary.
    baseline = analyze_rows(rows)
    changed = analyze_rows(perturbed)

    # Then: unknown successor exact metrics cannot flip the downstream classification.
    assert changed == baseline
    assert changed.downstream_feasibility == "indeterminate_non_exact_metrics"
    assert "dev_test_minimum_unavailable" not in changed.failure_reasons
