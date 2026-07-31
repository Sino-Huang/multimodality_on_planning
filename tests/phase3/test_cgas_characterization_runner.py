from __future__ import annotations

from pathlib import Path

import pytest

from cgas_characterization_runner_support import Sink, contract, execution, request

from scripts.phase3.cgas_characterization_runner import RunMode, RunnerError, run


def test_fresh_initializes_empty_work_without_characterizing(tmp_path: Path) -> None:
    # Given: a future finalized root and an injected characterizer that records calls.
    calls: list[str] = []
    run_request = request(tmp_path, "final")
    run_execution = execution(contract(0), calls, Sink())

    # When: fresh lifecycle initialization is requested.
    report = run(run_request, RunMode.FRESH, run_execution)

    # Then: it publishes only the empty durable work state and invokes no row characterization.
    assert calls == []
    assert report.characterized_count == 0
    assert (tmp_path / "final.work" / "checkpoints").is_dir()


def test_shard_processes_only_ascending_canonical_modulo_indices(tmp_path: Path) -> None:
    # Given: a fresh synthetic 481-row work root and the middle of three shards.
    run_request = request(tmp_path, "final", shard_count=3, shard_index=1)
    run_contract = contract()
    calls: list[str] = []
    sink = Sink()
    run_execution = execution(run_contract, calls, sink)
    run(run_request, RunMode.FRESH, run_execution)

    # When: the shard fills its assigned missing checkpoints.
    report = run(run_request, RunMode.SHARD, run_execution)

    # Then: its sole selection rule is canonical index modulo, in ascending order.
    assert calls == [f"synthetic-{index:04d}" for index in range(1, 481, 3)]
    assert report.characterized_count == len(calls) == sink.flush_count


def test_invalid_shard_index_rejects_before_characterization(tmp_path: Path) -> None:
    # Given: an out-of-range shard index and an observable injected characterizer.
    run_request = request(tmp_path, "final", shard_count=3, shard_index=3)
    calls: list[str] = []

    # When: any lifecycle operation receives the invalid boundary value.
    with pytest.raises(RunnerError, match="invalid_shard_index"):
        run(run_request, RunMode.FRESH, execution(contract(), calls, Sink()))

    # Then: it reaches neither state creation nor scientific work.
    assert calls == []


def test_fresh_normalizes_existing_work_root_error(tmp_path: Path) -> None:
    # Given: a pre-existing work root and an observable injected characterizer.
    run_request = request(tmp_path, "final")
    calls: list[str] = []
    (tmp_path / "final.work").mkdir()

    # When: fresh lifecycle initialization refuses to overwrite that state.
    with pytest.raises(RunnerError, match="fresh_root_exists"):
        run(run_request, RunMode.FRESH, execution(contract(), calls, Sink()))

    # Then: callers receive the runner's stable error type without characterization.
    assert calls == []
