# Compact knowledge archive index

Only two live notes remain in this directory:

- `calibration-pilot-sizing-2026-08-07.md` - cited directly by the research execution plan.
- `phase3-domain-safety-for-llm-research.md` - standing research/data boundaries.

The previous 22-note set, the historical work ledger, superseded production plan/status, session
logs, and legacy `.omo` task state are preserved in
`.claude/archive/context-hot-snapshot-2026-08-10.tar.gz` with SHA-256
`8b16b0231fd4d2eda359da80b3fdc16563a43eaa58828cc55d4456bb22ca45fc`.

Four post-snapshot session logs (`session-20260810-01a00ffc.md`, `session-20260810-9cfdb0cf.md`,
`session-20260810-f9c6ef25.md`, `session-20260811-c79a798d.md`) removed from retired `.claude/logs/`
are preserved byte-for-byte in `.claude/archive/session-logs-2026-08-10-to-2026-08-11.tar.gz` with
SHA-256 `61da47e64015cde758aaa8c82a13c4a2b5670236d7a16b880e99cc261e6bbd97`.

Prefer maintained sources in this order:

1. `doc/high_level_plans/research_execution_plan.md`
2. `task_plan.md` and `notes.md`
3. The milestone's archived `data/deprecated/2026-08-18-cgas-realignment/.claude/evidence/<milestone>/verification*.md`
   (historical records only; no active code or test may read the cold archive)
4. Git history via `git show HEAD:<old-path>`
5. The compressed snapshot for untracked or orchestration-only files

Do not restore archived notes into hot directories merely for browsing. Extract to a temporary
directory and promote only a still-valid conclusion into an existing canonical document.
