from __future__ import annotations

import multiprocessing
from collections.abc import Callable
from pathlib import Path

import pytest

from phase3_writer_output_layout_lock_support import (
    BLOCKED_POLL_SECONDS,
    EVENT_TIMEOUT_SECONDS,
    RecordingLock,
    WriterMutationError,
    apply_organizer,
    cleanup_writer,
    patch_pipeline_lifecycle,
    prepare_organizer_repository,
    start_writer,
    writer_module,
    writer_repository,
)
from phase3_writer_output_layout_lock_planimation_support import PlanimationMode, patch_planimation_lifecycle


def _recording_lock_factory(events: list[str], repositories: list[Path]) -> Callable[[Path], RecordingLock]:
    def recording_lock(repository: Path) -> RecordingLock:
        return RecordingLock(repository, events, repositories)

    return recording_lock


@pytest.mark.parametrize("raises", [False, True], ids=["completion", "exception"])
def test_pipeline_lock_releases_after_final_reports_or_late_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    raises: bool,
) -> None:
    # Given: a future writer lock binding and an absent external output root.
    module = writer_module("pipeline")
    expected_repository = writer_repository(module)
    output_root = tmp_path / "external-output-root"
    events: list[str] = []
    repositories: list[Path] = []
    monkeypatch.setattr(module, "shared_output_layout_lock", _recording_lock_factory(events, repositories), raising=False)
    run_writer = patch_pipeline_lifecycle(monkeypatch, events, raises, output_root)

    # When: the writer completes normally or its first mutation raises.
    if raises:
        with pytest.raises(WriterMutationError):
            run_writer()
    else:
        run_writer()

    # Then: the module-derived repository lock enclosed every observed mutation and released.
    assert not output_root.exists()
    assert repositories == [expected_repository]
    assert events[0:2] == ["acquired", "clear"]
    assert events[-2:] == ["reports", "released"]


@pytest.mark.parametrize(
    ("mode", "raises", "expected_events"),
    [
        pytest.param("render-only", False, ["acquired", "manifest", "render", "validate", "released"], id="render-only"),
        pytest.param("full", False, ["acquired", "manifest", "render", "records", "validate", "released"], id="full"),
        pytest.param("full", True, ["acquired", "manifest", "render", "records", "validate", "released"], id="late-validation-exception"),
    ],
)
def test_planimation_lock_encloses_render_and_full_lifecycles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: PlanimationMode,
    raises: bool,
    expected_events: list[str],
) -> None:
    # Given: an external output root and a recording future shared-lock binding.
    module = writer_module("planimation")
    output_root = tmp_path / "external-output-root"
    events: list[str] = []
    repositories: list[Path] = []
    monkeypatch.setattr(module, "shared_output_layout_lock", _recording_lock_factory(events, repositories), raising=False)
    run_writer = patch_planimation_lifecycle(monkeypatch, events, mode, raises, output_root)

    # When: rendering completes, the full path completes, or late validation raises.
    if raises:
        with pytest.raises(WriterMutationError):
            run_writer()
    else:
        run_writer()

    # Then: the lock retains through each terminal validation path and releases afterward.
    assert not output_root.exists()
    assert repositories == [writer_repository(module)]
    assert events == expected_events


def test_shared_writers_coexist_and_hold_organizer_until_both_release(tmp_path: Path) -> None:
    # Given: two spawned writers targeting a synthetic module-derived repository.
    repository = prepare_organizer_repository((tmp_path / "repository").resolve())
    context = multiprocessing.get_context("spawn")
    first = start_writer(context, "planimation", repository)
    second = start_writer(context, "pipeline", repository)
    completed_receiver, completed_sender = context.Pipe(duplex=False)
    lock_receiver, lock_sender = context.Pipe(duplex=False)
    organizer = context.Process(target=apply_organizer, args=(repository, completed_sender, lock_sender))
    organizer_started = False
    try:
        assert first.entered.poll(EVENT_TIMEOUT_SECONDS)
        assert first.entered.recv() == "planimation"
        assert second.entered.poll(EVENT_TIMEOUT_SECONDS)
        assert second.entered.recv() == "pipeline"
        assert not (repository / ".phase3-output-layout.lock").exists()
        organizer.start()
        organizer_started = True
        completed_sender.close()
        lock_sender.close()

        # When: the actual exclusive organizer operation contends with both shared writers.
        assert lock_receiver.poll(EVENT_TIMEOUT_SECONDS)
        assert lock_receiver.recv() == "attempting"
        assert not lock_receiver.poll(BLOCKED_POLL_SECONDS)
        first.release.send("release")
        first.process.join(EVENT_TIMEOUT_SECONDS)
        assert first.process.exitcode == 0
        assert not lock_receiver.poll(BLOCKED_POLL_SECONDS)
        second.release.send("release")
        second.process.join(EVENT_TIMEOUT_SECONDS)

        # Then: both shared writers coexist, and the organizer completes only after both release.
        assert second.process.exitcode == 0
        assert lock_receiver.poll(EVENT_TIMEOUT_SECONDS)
        assert lock_receiver.recv() == "acquired"
        assert completed_receiver.poll(EVENT_TIMEOUT_SECONDS)
        assert completed_receiver.recv() == "complete"
        organizer.join(EVENT_TIMEOUT_SECONDS)
        assert organizer.exitcode == 0
    finally:
        cleanup_writer(first)
        cleanup_writer(second)
        if organizer_started:
            if organizer.is_alive():
                organizer.terminate()
            organizer.join(EVENT_TIMEOUT_SECONDS)
        completed_receiver.close()
        completed_sender.close()
        lock_receiver.close()
        lock_sender.close()
