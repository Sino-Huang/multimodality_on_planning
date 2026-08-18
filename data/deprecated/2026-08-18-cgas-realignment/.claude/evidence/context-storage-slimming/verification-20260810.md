# Agent Context Storage Slimming Verification

## Result

- Archived hot/orchestration surface: 456,561 bytes.
- Live replacement surface: 16,944 bytes.
- Reduction: 439,617 bytes (96.3%).
- Live knowledge: 5 Markdown files, 12,668 bytes.
- Load-bearing `.claude/evidence/` artifacts were not moved or deleted.
- Existing staged Phase 3 rendering files were not unstaged or overwritten.

The byte-exact recovery snapshot is
`.claude/archive/context-hot-snapshot-2026-08-10.tar.gz`, SHA-256
`8b16b0231fd4d2eda359da80b3fdc16563a43eaa58828cc55d4456bb22ca45fc`.
The archived historical ledger has SHA-256
`303693018880cd588e84e35078f71109893a04a8a410adce22c7ee95b3d3914c`.

## Verification

```bash
bash scripts/check_agent_context_budget.sh
tar -tzf .claude/archive/context-hot-snapshot-2026-08-10.tar.gz
git diff --check
git diff --staged --check
```

Expected budget signal:

```text
agent context budget OK: files=5 knowledge_bytes=12668 orientation_bytes=16944
```

The cleanup is intentionally unstaged so it remains separate from the already staged Phase 3
rendering milestone. A fresh agent session should use `.claude/README.md` as the orientation entry
point and open individual evidence files only when referenced by the active task.
