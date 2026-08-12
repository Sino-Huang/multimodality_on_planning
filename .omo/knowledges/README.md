# Cross-harness knowledge policy

This is a compatibility surface for harnesses that require `.omo/knowledges/*.md`. Keep one rolling
closeout for the active milestone and update it in place. Do not create per-session, per-agent,
per-test, or per-review notes.

Canonical state lives in `doc/high_level_plans/research_execution_plan.md`, `task_plan.md`,
`notes.md`, and the active milestone's `.claude/evidence/` verification summary. Completed `.omo`
notes are archived in `.claude/archive/context-hot-snapshot-2026-08-10.tar.gz` and tracked versions
remain recoverable through Git history.

Combined `.claude/knowledge/` and `.omo/knowledges/` content must stay below 25 KB and six Markdown
files. When the active milestone changes, consolidate its prior closeout into canonical docs before
replacing it.
