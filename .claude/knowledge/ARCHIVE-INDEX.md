# Compact knowledge archive index

Only two live notes remain in this directory:

- `calibration-pilot-sizing-2026-08-07.md` - cited directly by the research execution plan.
- `phase3-domain-safety-for-llm-research.md` - standing research/data boundaries.

The previous 22-note set, the historical work ledger, superseded production plan/status, session
logs, and legacy `.omo` task state are preserved in
`.claude/archive/context-hot-snapshot-2026-08-10.tar.gz` with SHA-256
`8b16b0231fd4d2eda359da80b3fdc16563a43eaa58828cc55d4456bb22ca45fc`.

Prefer maintained sources in this order:

1. `doc/high_level_plans/research_execution_plan.md`
2. `task_plan.md` and `notes.md`
3. The active milestone's `.claude/evidence/<milestone>/verification*.md`
4. Git history via `git show HEAD:<old-path>`
5. The compressed snapshot for untracked or orchestration-only files

Do not restore archived notes into hot directories merely for browsing. Extract to a temporary
directory and promote only a still-valid conclusion into an existing canonical document.
