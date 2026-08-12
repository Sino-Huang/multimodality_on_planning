from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import pytest

HARNESS_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "evidence"
    / "cgas-phase3-pilot-rendering"
    / "local_planimation_adapter_integration.py"
)


def _load_harness() -> types.ModuleType:
    """Import the loopback harness from its non-package location under .claude.

    The harness has no import-time side effects (no server, no HTTP, no git), so
    loading it is safe for exercising its pure guards and constants.
    """
    spec = importlib.util.spec_from_file_location("local_planimation_adapter_integration", HARNESS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_harness_refuses_non_loopback_urls() -> None:
    harness = _load_harness()
    for invalid_url in (
        "https://example.com/upload/pddl",
        "http://192.168.1.1/upload/pddl",
        "ftp://127.0.0.1/upload/pddl",
    ):
        with pytest.raises(harness.ProofError) as excinfo:
            harness._assert_loopback_url(invalid_url)
        assert excinfo.value.reason == "refusing_non_loopback_url"
    harness._assert_loopback_url("http://127.0.0.1:8000/upload/pddl")
    harness._assert_loopback_url("http://localhost:8000/upload/pddl")


def test_harness_fixture_is_synthetic_4_object_not_production_fixture() -> None:
    harness = _load_harness()
    assert harness.FIXTURE_OBJECT_COUNT == 4
    assert harness.FIXTURE_OBJECT_COUNT not in (8, 12)  # never the mapping-bound 8-obj / representative 12-obj
    assert harness.FIXTURE_RAW_RANK == 0
    assert harness.PLAN_ACTIONS == ["(pickup b1)"]


def test_harness_profile_materialization_changes_only_randocolor_sentinel() -> None:
    harness = _load_harness()
    profile = "(define (animation blocksworld)\n  (color RANDOMCOLOR)\n  (color RED)\n)"
    materialized = harness._materialize_profile_text(profile)
    assert "(color GREY)" in materialized
    assert "RANDOMCOLOR" not in materialized
    assert "(color RED)" in materialized  # unrelated text untouched
    assert harness._materialize_profile_text("no sentinel present") == "no sentinel present"
    assert harness._materialize_profile_text(materialized) == materialized  # idempotent


def test_harness_output_root_guard_fails_closed_before_any_server(tmp_path: Path) -> None:
    harness = _load_harness()
    existing = tmp_path / "exists"
    existing.mkdir()
    assert harness.main(["--output-root", str(existing)]) == 2


def test_harness_report_wording_does_not_overclaim_network_interception() -> None:
    source = HARNESS_PATH.read_text(encoding="utf-8")
    # The report basis must explicitly limit the observable to the integrated
    # client requests and disclaim any network-level interception of the backend.
    assert "no claim of network-level interception" in source
    assert "integrated client path" in source
    assert "hosted_requests" in source
