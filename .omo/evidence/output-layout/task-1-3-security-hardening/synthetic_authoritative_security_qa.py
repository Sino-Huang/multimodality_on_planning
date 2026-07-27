from __future__ import annotations

import pytest


def main() -> int:
    scenarios = (
        "tests/phase3/test_output_layout_acceptance_security.py::test_protected_content_fifo_substitution_before_regular_file_open_is_nonblocking",
        "tests/phase3/test_output_layout_snapshot_adversarial.py::test_snapshot_fifo_substitution_before_regular_file_open_is_nonblocking_and_normalized",
        "tests/phase3/test_output_layout_view_races.py::test_private_stage_walkers_reject_synthetic_depth_and_entry_limits",
        "tests/phase3/test_output_layout_view_races.py::test_partial_private_stage_construction_preserves_primary_failure_and_only_cleans_owned_entries",
        "tests/phase3/test_output_layout_view_races.py::test_stage_cleanup_retains_racer_replacement_after_quarantine_validation",
        "tests/phase3/test_output_layout_receipt_adversarial.py::test_receipt_cleanup_retains_racer_sidecar_after_quarantine_validation",
        "tests/phase3/test_output_layout_view_races.py::test_public_final_racer_substitution_after_publish_is_not_retained",
        "tests/phase3/test_output_layout_receipt_adversarial.py::test_recovery_sidecars_require_exact_private_mode_at_read_and_cleanup",
    )
    return pytest.main(["-q", *scenarios])


if __name__ == "__main__":
    raise SystemExit(main())
