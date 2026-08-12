# Agent working state

This directory is intentionally small at the orientation layer. Do not recursively read `.claude/`
or preload evidence. Start from the canonical sources below and open only the evidence named by the
active task.

## Start here

1. `../doc/high_level_plans/research_execution_plan.md` - canonical research sequence and gates.
2. `../task_plan.md` and `../notes.md` - active milestone and current execution facts.
3. `production-p0-status.md` - compact current-state pointer.
4. `knowledge/calibration-pilot-sizing-2026-08-07.md` and
   `knowledge/phase3-domain-safety-for-llm-research.md` - the only retained live research notes.
5. `.omo/knowledges/cgas-phase3-pilot-rendering-closeout-2026-08-10.md` - current cross-harness
   closeout while the rendering milestone remains staged.

## Context budget

- Keep `.claude/knowledge/` plus `.omo/knowledges/` below 25 KB and six Markdown files.
- Maintain one rolling closeout for the active milestone. Update it instead of creating per-session,
  per-agent, or per-verification notes.
- Put commands and raw receipts in the owning `.claude/evidence/<milestone>/` directory. Never read
  all evidence into context; use its README or verification summary to select individual files.
- Completed plans, ledgers, logs, and notes belong in the compressed archive or Git history.
- Do not store session transcripts, repeated test output, or tool narration as project knowledge.

Run the enforced budget check after changing agent-facing storage:

```bash
bash scripts/check_agent_context_budget.sh
```

## Load-bearing evidence

Do not move `.claude/evidence/` wholesale. Some paths are referenced by tests or approved research
contracts. The active research plan and milestone notes name the evidence that matters. All other
evidence is cold and should be opened only for a specific verification question.

## Recovery

The pre-slimming hot context is preserved byte-for-byte in
`.claude/archive/context-hot-snapshot-2026-08-10.tar.gz` (SHA-256
`8b16b0231fd4d2eda359da80b3fdc16563a43eaa58828cc55d4456bb22ca45fc`). The earlier pre-migration
evidence archive remains `.claude/archive/omo-evidence-2026-08-07.tar.gz`. Both are gitignored.
Tracked files are also recoverable with `git show HEAD:<path>`; use Git history in a fresh clone
where the local archives are absent.

```bash
tar -tzf .claude/archive/context-hot-snapshot-2026-08-10.tar.gz
mkdir -p /tmp/cgas-context-recovery
tar -xzf .claude/archive/context-hot-snapshot-2026-08-10.tar.gz -C /tmp/cgas-context-recovery
```
