# Production P0 server-restart handoff - 2026-08-06

## Requested stop

- At `2026-08-06T16:09:36+10:00`, the user requested a safe stop before restarting the server.
- The sole round-2 writer was PID `108645` in tmux session `cgas-production-round2`.
- It received exactly one terminal `SIGINT` through `tmux send-keys -t cgas-production-round2 C-c` and exited within one second.
- No `SIGTERM`, `SIGKILL`, deletion, rollback, or replacement process was used.
- The tmux session and both root watcher shells exited. No matching characterization process remains.
- `.omo/boulder.json` was removed after a paused status still triggered automatic continuation; the next session must explicitly resume the plan from this handoff and ledger.

## Exact interruption point

The run had finished generating its reusable trace streams and was inside checkpoint construction, validating persisted trace-v2 streams:

```text
cgas_candidate_characterization_runner._consume_round
  -> cgas_candidate_characterization_checkpoint.build_checkpoint
  -> validate_checkpoint
  -> validate_trace_binding
  -> verify_trace_stream
  -> KeyboardInterrupt
```

The interrupted log is:

- `.claude/evidence/production-p0-corpus-experiment-readiness/task-3/round-2/round-2.log`
- SHA-256 `a527a61bd39b5fde434f42727dfe61b8105d14d76b23ca07fdd7c9b64bc724c1`
- Size `2182` bytes

The wrapper did not publish `exit-code.txt`, because `Ctrl-C` terminated the tmux foreground command before the shell reached its receipt write.

## Runtime evidence before stop

The live-process diagnosis is:

- `.claude/evidence/production-p0-corpus-experiment-readiness/task-3/round-2/runtime-stack-diagnosis.md`
- SHA-256 `a1e7bf26480a81f62a294e0cc35bde9c3928f55d57269b7c6ae1191f5dfb1d4f`

Three samples showed PID `108645` at about 99.5% CPU while the same BFS stream file descriptor advanced from `14,134,804,480` to `16,638,803,968` bytes in 30 seconds. The process was productive. The apparent two-hour no-mtime interval was caused by reading/validating an already published stream, not a fixed-state loop.

## Immutable state after stop

- Round-2 checkpoint is absent: `tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000002.json` does not exist.
- `current.json` still points to round 1 and has SHA-256 `1b23b2c76fb1b77b85a0549b89fc5b4e3c503668e03c46db6443650b64fcacdf`.
- Round-1 checkpoint remains SHA-256 `fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853`.
- Selector attempt 1 remains SHA-256 `4a594ae9a43214aeac772f10badae2d1559db60c19e77ac10a4a9f2be01c4c60` with `selector_infeasible` / `calibration_exact_39_unavailable`.
- The trace root contains `558` directories, `558` complete `bfs.trace-v2.jsonl` files, and `558` complete `iw.trace-v2.jsonl` files.
- No `.*trace-v2.jsonl-*`, `*.tmp`, or `*.partial` file remained after the stop.
- Todo 3 remains checked because its implementation/replay contract was already independently confirmed. Todo 4 remains unchecked and in progress.

## Safe resume command

After the server restart, first confirm no writer exists and recheck the three immutable digests above. Then resume the exact same round-2 request in a new tmux session. Use a new log/exit-code path so the interruption evidence is preserved:

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
ps -eo pid=,cmd= | rg 'scripts.phase3.cgas_candidate_characterization next-round' || true
sha256sum \
  tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json \
  tmp/cgas-p0-characterized/current.json \
  tmp/cgas-production-population/selector_attempt_000001.json
tmux new-session -d -s cgas-production-round2-resume \
  "cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning && source ~/cd_vlaplan && python -m scripts.phase3.cgas_candidate_characterization next-round --round 2 --checkpoint tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json --feedback tmp/cgas-production-population/selector_attempt_000001.json --approved-trace-contract .claude/evidence/cgas-production-p0/approved-trace-v2.json --candidate-config configs/cgas/production_p0_candidates.json --candidate-root tmp/cgas-p0-candidates --output tmp/cgas-p0-characterized --json > .claude/evidence/production-p0-corpus-experiment-readiness/task-3/round-2/round-2-resume.log 2>&1; code=\$?; printf '%s\\n' \"\$code\" > .claude/evidence/production-p0-corpus-experiment-readiness/task-3/round-2/exit-code-resume.txt; exit \"\$code\""
```

Do not launch a second copy while that tmux command is active. Existing streams must be reused only through the normal verifier/replay path. Expect a long read-only verification pass over large streams before checkpoint 2 can publish.

## Next-session TODOs

1. Read `.claude/plans/production-p0-corpus-experiment-readiness.md`, `.claude/ledger.jsonl`, this handoff, and the round-2 evidence directory before acting.
2. Recreate/resume Boulder state through the `start-work` workflow, then confirm no matching writer, stale tmux session, or temporary trace file exists.
3. Resume round 2 with the exact command above; do not delete or regenerate the 558 complete stream pairs.
4. On exit 0, capture checkpoint-2 SHA-256, `current.json` binding, accounting/characterization/reservoir counts, cursor deltas, predecessor and feedback digests, and cleanup receipt.
5. Dispatch an independent Oracle/gate reviewer for round-2 artifact verification. A worker DoneClaim alone is not sufficient.
6. Only after round 2 is confirmed, run Todo 4 against the new `current.json` to produce selector attempt 2.
7. If attempt 2 is infeasible, keep Todo 4 unchecked and feed the exact immutable result into the next Todo 3 round. If it is `selector_feasible`, require exact 481-row re-characterization/parity and independent confirmation before checking Todo 4.
8. Todos 5-16 and F1-F4 remain dependency-gated. No commit or PR is authorized.

## Worktree constraints

- Preserve the heavily dirty shared worktree and all unrelated edits.
- Never use `git clean`.
- Use `source ~/cd_vlaplan` for Python commands.
- Trace-v1 release digest must remain `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`.
- Todo 4 alone emits selector feedback; Todo 3 alone advances cursors.
