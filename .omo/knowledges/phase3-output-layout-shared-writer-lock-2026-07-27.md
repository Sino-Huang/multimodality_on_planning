# Phase 3 Output-Layout Shared Writer Lock

Phase 3 writers select the output-layout lock from the repository, not from the output root. Both use `shared_output_layout_lock(Path(__file__).resolve().parents[2])`, so coordination remains stable when an output root is absent, temporary, or outside the repository. Output-root validation and policy remain separate and unchanged.

`generate_planimation_vlm.main` acquires the shared lock immediately before `build_pairing_manifest`. The protected lifetime includes manifest-only completion, replay rendering, render-only validation, VLM record generation, final validation, every return, and exceptions.

`pipeline.generate_supervised_data` keeps planner validation, the jobs guard, and limits construction outside the lock. It acquires the shared lock immediately before `clear_output_root` and retains it through `_write_reports`, return, and exceptions.

Focused lifecycle tests should cover normal returns and late exceptions, not only lock entry. Process-level proof should use spawned writers, the real `fcntl` shared and exclusive primitives, pipe events for causal synchronization, and the real organizer `apply`. The exclusive organizer must remain blocked while either shared writer still holds the lock. The retained shared contention test asserts the absence of `.phase3-output-layout.lock`, and its test support uses the canonical synthetic receipt path `outputs/deprecated/phase3/output_reorganization_20260726.json`.

Verification commands:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp uv run --no-project --with typing_extensions --with pytest pytest -q --tb=short tests/phase3/test_phase3_writer_output_layout_lock.py
# 6 passed in 2.81s
```

Observed latest result on 2026-07-27: the focused writer suite passed 6 tests in 2.81s. The two named organizer overlay regressions passed in 2.47s. The base environment lacked `typing_extensions`, so both runs used the temporary `uv run --no-project --with typing_extensions --with pytest` overlay after the required environment prefix. No permanent dependency was installed, and no project environment or dependency file was changed.

The latest Lane 1 lock evidence is the interruption-cleanup follow-up. It records 32 collected lock tests, 32 passed in 8.44s, and a dedicated 4-case KeyboardInterrupt GREEN after the preserved 4-failure RED. Earlier 28-test receipts remain preserved as prior evidence but are superseded for final status. The lock cleanup now tracks acquisition state, conditionally unlocks after flock has returned, and always closes the descriptor. Oracle has not yet been re-consulted after that remediation.

This evidence pass did not edit organizer or writer product files, access or change real outputs, change or delete the root `.phase3-output-layout.lock`, edit dependency files, or create a commit.
