# Deadline research plan

The deadline study uses one seed (17), a small matched comparison and fixed wall
time budgets. This supersedes the full-matrix requirements in issues #75–#109.
Original ticket bodies and comments are retained in `original-issues.json`;
`revised-issues.json` records the replacement titles and bodies. Deferred tickets
remain open, preserving their history without blocking the deadline release.

## Required execution order

```text
75 → 76 → 77
           ├─ stop:     100 → 108 (development feasibility/limitations only)
           └─ continue: 90 → 91 → 92 → 93 → 94 → 95 → (97 || 109) → 100 → 108
```

#75 and #76 are logically independent, as are #93–#95 after their prerequisites.
Execute their GPU stages sequentially because each may use both available A100s.
CPU preparation can overlap where dependencies permit. Give concurrent workers
distinct explicit MASTER_PORT values; GPU isolation does not isolate ports.

| Ticket | Work | Maximum wall time for GPU stage |
| --- | --- | ---: |
| #75 | Visual development pilot | 4 hours |
| #76 | Matched multimodal development pilot | 4 hours |
| #93 | Matched text training and final evaluation | 4 hours |
| #94 | Final visual evaluation using pilot adapters | 2 hours |
| #95 | Final multimodal evaluation using pilot adapters | 2 hours |
| Total | Primary GPU stages, serialized on two A100s | 16 hours |

These are spending caps, not runtime forecasts or guarantees of completion. They
exclude implementation, CPU preparation and writing, and are not GPU-hours.
#91 and #92 each have at most one hour of local preparation. #77, #90, #97, #109,
#100 and #108 add no model calls. #77 may stop the study before final evaluation
if the development evidence is incomplete, invalid or uninformative. Record actual
compute, including earlier attempts, separately from this remaining-work budget.

## Matched scope

#75 uses `configs/experiments/issue75/pilot.json` and `pilot-plan-v1.json`:
512 complete training records per algorithm, one epoch, global batch 32 (16
optimizer updates), at most 32 diagnostic records per algorithm, seed 17.
The evaluation panel has storage, blocksworld and ferry, four algorithms, and
12 algorithm/task cases. Base, SFT, random-valid and exact-reference controls
produce 48 development episodes. Training records are balanced across available
source domains under a 4,096-token visual input cap, then ordered easy to hard.
Text and multimodal work must use those exact IDs and the same schedules,
Search Memory, candidate information, task membership and episode budgets.
No source corpus, images, facts or planning traces are rewritten or truncated.

#76 must qualify its actual multimodal processor/model inputs within its budget;
visual hardware qualification does not certify another modality. #93 trains the
matched text comparison if no compatible adapter exists. #90 freezes the final
protocol before evaluating held-out outcomes. #91 selects one new, inexpensive
problem per domain, matched across all four algorithms and three modalities,
using declared reference-cost/layout limits. No test-outcome-based task selection
or checkpoint tuning is allowed. #94/#95 reuse final pilot adapters.

The final three-problem, one-seed result is a limited pilot. It cannot establish
broad generalization, seed variance, architecture replication or transfer. #97
and #109 derive only valid diagnostics from retained traces. A different budget
that would change model behavior cannot be reconstructed as a counterfactual
result from an incompatible trace.

## Optional DAgger

```text
77 → 78 → 79 → (80 OR 81 OR 82) → 83 → 84
```

Run this only if #77 justifies it, and finish before #90 if including its adapter
in final evaluation. The entire branch shares **two hours**, not two hours per
ticket: one algorithm/modality cell, one iteration, seed 17, at most 64 expert
corrections from training tasks, at most 512 combined training records and one
epoch (at most 16 updates). #80, #81 and #82 are alternatives, not three required
parallel collections. Otherwise skip the branch; it does not block #90/#100.

## Deferred beyond the deadline study

- #85–#89: full-state end-to-end development.
- #96, #98, #99: broad structural generalization, robustness and end-to-end final evaluation.
- #101–#103: second-backbone replication.
- #104–#107: transfer registration and FOLIO/HumanEval/GSM8K runs.

#108 now follows #100 without replication or transfer prerequisites. These
extensions have zero allocated deadline compute and remain unmeasured. Reopening
active execution later requires a fresh bounded plan, not automatic restoration
of the old multi-seed matrix.

## Run the implemented visual pilot

```bash
source ~/cd_vlaplan
python scripts/run_visual_issue75.py all --dry-run
python -u scripts/run_visual_issue75.py all
```

The output is `outputs/visual_development/issue75-deadline-pilot-v1/attempt-001`.
The local renderer must be running as described in the #75 configuration README.
Terminal progress and worker log files include completed/total, elapsed time,
ETA where measurable, and 20-second heartbeats. New calls stop at 3h45m; the
runner terminates its own workers at 4h and preserves incomplete evidence.
Do not overlap this command with an older full-size #75 run. The old configuration
is retained only for explicit historical reproduction and has no live wall cap.
No new GPU experiment was launched when implementing this plan. The other active
tickets still require implementation and verification within their revised scopes.

A ticket may close with the evidence its revised criteria require, including a
fully collected negative pilot. Partial coverage must never be marked complete.
#100/#108 distinguish completed, incomplete, skipped and deferred work and state
whether the release is a held-out comparison or only development feasibility.
