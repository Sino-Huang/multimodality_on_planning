# Agent working state

This directory is intentionally small at the orientation layer. Do not recursively read `.claude/`
or preload evidence. Start from the canonical sources below and open only the evidence named by the
active task.

## Start here

1. GitHub issue #38 (`Spec: Teach VLMs executable search processes across modalities`) and its
   ready-for-agent tickets #39-#108 - the active research execution tree.
2. `../CONTEXT.md` - the #38-first glossary; historical CGAS terms are retained but demoted.
3. `../docs/high_level_plans/research_execution_plan.md` and
   `../docs/partial_obsolescence_exceptions.md` - retained research sequence, gates, and the
   register of mixed retained/obsolete material.
4. `../task_plan.md` and `../notes.md` - current execution facts (their CGAS framing is stale;
   see the exceptions register).
5. `production-p0-status.md` - compact current-state pointer.
6. `knowledge/calibration-pilot-sizing-2026-08-07.md` and
   `knowledge/phase3-domain-safety-for-llm-research.md` - the only retained live research notes.

## Context budget

- Keep `.claude/knowledge/` below 25 KB and six Markdown files.
- Maintain one rolling closeout for the active milestone. Update it instead of creating per-session,
  per-agent, or per-verification notes.
- Completed plans, ledgers, logs, and notes belong in the compressed archive or Git history.
- Do not store session transcripts, repeated test output, or tool narration as project knowledge.

Run the enforced budget check after changing agent-facing storage:

```bash
bash scripts/check_agent_context_budget.sh
```

## Cold evidence archive

All former `.claude/evidence/` and `.omo/` state was moved on 2026-08-18 to the cold archive at
`../data/deprecated/2026-08-18-cgas-realignment/` with original repository-relative paths preserved.
No active code or test may read, import, or otherwise depend on that archive. Current #38 work uses
the active fixtures and contracts named by the active ticket, not archived evidence. Mixed
retained/obsolete files are indexed in `../docs/partial_obsolescence_exceptions.md`.

## Recovery

The pre-slimming hot context is preserved byte-for-byte in
`.claude/archive/context-hot-snapshot-2026-08-10.tar.gz` (SHA-256
`8b16b0231fd4d2eda359da80b3fdc16563a43eaa58828cc55d4456bb22ca45fc`). Four post-snapshot session
logs (`session-20260810-01a00ffc.md`, `session-20260810-9cfdb0cf.md`,
`session-20260810-f9c6ef25.md`, `session-20260811-c79a798d.md`), removed from retired `.claude/logs/`,
are preserved byte-for-byte in `.claude/archive/session-logs-2026-08-10-to-2026-08-11.tar.gz`
(SHA-256 `61da47e64015cde758aaa8c82a13c4a2b5670236d7a16b880e99cc261e6bbd97`). The earlier
pre-migration evidence archive remains `.claude/archive/omo-evidence-2026-08-07.tar.gz`. All three
archives are gitignored. Tracked files are also recoverable with `git show HEAD:<path>`; use Git
history in a fresh clone where the local archives are absent.

```bash
tar -tzf .claude/archive/context-hot-snapshot-2026-08-10.tar.gz
mkdir -p /tmp/cgas-context-recovery
tar -xzf .claude/archive/context-hot-snapshot-2026-08-10.tar.gz -C /tmp/cgas-context-recovery
```
