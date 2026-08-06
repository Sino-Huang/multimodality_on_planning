# Production P0 corpus / experiment readiness — session status

**`.claude/` is authoritative** as of the 2026-08-07 migration; `.omo/` and `.sisyphus/` are gone.
See `.claude/README.md` for the layout and for how to recover anything archived.

Last updated: 2026-08-07 (owner ruled; research execution plan revised to revision 2)

## Current state

**UNBLOCKED BY DECISION — the path forward changed.** The owner ruled on the decision packet and
`doc/high_level_plans/research_execution_plan.md` was rewritten as **revision 2**. Read that
document and `.claude/knowledge/research-execution-plan-revision-2-2026-08-07.md` before acting;
the sections below describe the *superseded* v2-contract situation and are kept for context.

Four decisions taken:

1. **Raise IW to true iterative width 1→2** — not a quota change. Measuring per planner shows
   IW-exact ⊂ BFS-exact exactly (14/14, 23/23, 16/16), so "paired-exact" was only ever
   "IW-exact", and BFS alone solves 100% of the 4-object universe. The block was a
   planner-configuration defect.
2. **Drop the three redundant BFS snapshot fields** — 2.25 TB/round → ~6.6 GB. This is what
   makes decision 1 affordable.
3. **No starVLA; three backbones not four** — Phase 4 moves to a standalone `planning_vlm/`.
4. **Re-derive corpus scale from experiment needs** — `EXPECTED_*` become derived quantities.

Decisions 1 and 2 ship as **one** contract (v3), one owner approval, one regeneration.

**Recommended next milestone: the Phase A probe** — run IW at width 1→2 over the already-enumerated
raw ranks and report the exact rate per object count. It needs no approval, costs hours, and either
confirms the direction or sends the corpus question back to the owner.

**Two defects must be fixed in v3 before any width-2 corpus:** `run_iterated_width` does not
actually iterate (so `width_decision` is a constant), and `MAX_IW_TRACE_NOVELTY_ITEMS = 200`
truncates the accumulated novelty table — safe at width 1 (max observed 150) but overflowing at
width 2 (325 / 3,321 / 14,365 for n=4/8/12), which would make `seen_feature_delta` unsound.

## Superseded context — the v2-contract block

3 of 20 top-level todos complete. Todo 3 is checked and independently confirmed. Todo 4 is
unchecked and cannot be completed under the *old* constants. No commit or PR.

The decision packet that prompted the ruling:
`.claude/evidence/production-p0-corpus-experiment-readiness/task-4/owner-decision-packet/DECISION.md`.

**Disk:** round-1 BFS traces are 2.20 TiB against 1.27 TiB free, so **0.58 rounds fit**. No further
round can run under the v2 contract.

The selector hard-requires **190 paired-exact 4-object rows**
(`scripts/phase3/cgas_partition_contracts.py:11`, enforced at
`scripts/phase3/cgas_production_population_manifest.py:43-49`, with every row forced through
`_paired_exact` at line 24). The 4-object candidate universe is **closed at 210** distinct
nontrivial identities and its stream is already `exhausted: true`. Round 1 characterized 88 of
them and got **14** paired-exact (15.9%). Ceiling = 14 + 122 = **136 < 190**. Expected ≈ 33.

No further Todo 3 round can change this. Awaiting an owner decision on `EXPECTED_OBJECT_COUNTS[4]`;
the plan forbids the worker from altering quotas, so no remediation was proposed.

Only `n=4` is blocked. `n=8` (capacity 19,514,880) and `n=12` (capacity 2.84e12) are open, so
their quotas are a cost question rather than a feasibility one.

## Read these first

| Path | What it is |
| --- | --- |
| `.claude/plans/production-p0-corpus-experiment-readiness.md` | The approved plan (do not edit) |
| `.../task-4/owner-decision-packet/DECISION.md` | **The packet awaiting an owner ruling. Start here.** |
| `.../task-4/selector-infeasibility-proof/` | The proof, derivation, preconditions, re-runnable scripts |
| `.claude/knowledge/production-p0-owner-decision-packet-2026-08-06.md` | What the packet found and why it reorders the plan |
| `.claude/knowledge/production-p0-todo4-infeasibility-2026-08-06.md` | Why round 2 was not run |
| `.claude/ledger.jsonl` | Append-only; latest entry is `research-plan-revised` / `plan-revised` |

## Immutable digests — must not change

```
fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853  checkpoint 1
1b23b2c76fb1b77b85a0549b89fc5b4e3c503668e03c46db6443650b64fcacdf  current.json (binds round 1)
4a594ae9a43214aeac772f10badae2d1559db60c19e77ac10a4a9f2be01c4c60  selector attempt 1
3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3  trace-v1 release
b739f14869303002d0006dbb0be5b4042835002d289c23ee61ee87ac19323e51  proof.json
```

`tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000002.json` must remain **absent**
unless round 2 is deliberately authorized and completes.

## Reusable artifacts — never delete or regenerate

558 trace directories, 558 complete `bfs.trace-v2.jsonl` (2.25 TB), 558 complete
`iw.trace-v2.jsonl` (0.07 GB). No `.tmp`, `.partial`, or `.*trace-v2.jsonl-*` files.

## Before doing anything

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
E=.claude/evidence/production-p0-corpus-experiment-readiness/task-4/selector-infeasibility-proof
bash "$E/capture-preconditions.sh"          # six read-only precondition checks
source ~/cd_vlaplan && python "$E/derive_infeasibility.py"   # re-derives the proof
```

Note `ps` is aliased to `procs` and `du` to `dust` in this shell — use the `/proc` walk in
`capture-preconditions.sh` or `/usr/bin/ps` for process checks. Run `df` against the **project
path**, not `/data/scratch`: the project quota (~11 T, 1.4 T free, 87%) is the binding
constraint, while `/data/scratch` reports the whole 692 T filesystem.

## Round 2 — cannot succeed, and no longer fits

All six preconditions are clean, so the resume command in
`.claude/knowledge/production-p0-todo4-infeasibility-2026-08-06.md` is still syntactically valid.
It cannot produce `selector_feasible`, and it now **cannot complete at all**: a round comparable
to round 1 needs ~2.20 TiB against 1.27 TiB free, so it would fill the project quota partway
through, before producing a checkpoint. Do not run it.

## Standing constraints

- Never `git clean`. Preserve the heavily dirty shared worktree and all unrelated edits.
- Use `source ~/cd_vlaplan` for Python.
- No commits, no PRs.
- Todo 3 alone advances cursors; Todo 4 alone emits selector feedback.
- Never weaken quotas, selector constants, planner limits, or trace completeness.
- Never run duplicate long characterization or replay processes.
- Do not recreate a `boulder.json` auto-continuation file anywhere — the orchestration tool that
  used it was retired in the 2026-08-07 migration.
