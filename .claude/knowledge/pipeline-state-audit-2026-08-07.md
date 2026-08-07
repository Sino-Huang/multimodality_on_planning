---
name: pipeline-state-audit
description: What is actually built between candidates and a trained model — the end-to-end path works at 12-step fixture scale, but five production modules and the whole planning_vlm package are absent.
metadata:
  type: project
---

Audited 2026-08-07 by checking for modules and tests directly, rather than reading todo checkboxes.
Re-run the checks before trusting this if much has changed.

## The path works end to end — at 12 steps

`data/planning_cgas_v1/qwenvl/` holds real `train/dev/test.jsonl` produced from candidates through
traces, certificates, renders, alignment, and conversion. It is **12 steps across 4 instances**.
The last mile exists and is proven: `cgas_qwenvl.build_corpus(source_root, alignment_root,
corpus_root)`.

Rendering is not the bottleneck it looks like. It depends on an external service
(`https://planimation.planning.domains`, upload + local VFG render, 3 attempts, 90s timeout), but
**62,292 PNGs already exist under `outputs/image_frames/`** from earlier phase-3 work, and the
service responded HTTP 200 in 23ms when checked. The machinery scales; the failure modes are known
and have regression canaries.

**Two A100 80GB GPUs are visible.** Compute is not gating anything.

## What is absent

| Todo | Module | State |
|---|---|---|
| 5 | `cgas_production_review_packet` | missing (no test either) |
| 6 | `cgas_partition_materialize` | missing (no test either) |
| 7 | `cgas_production_staging` | missing (no test either) |
| 8 | `cgas_certificates_alignment_binding` | missing (no test either) |
| 10 | `cgas_production_release` | missing (no test either) |
| 9, 11–16 | `planning_vlm/` **and** `tests/planning_vlm/` | neither directory exists |

Present and working either side of that gap: `cgas_certificates.py`, `cgas_alignment.py`,
`cgas_release_gate.py`, `cgas_partition_selection.py`, `cgas_qwenvl*.py`.

So there is **no training code of any kind**, and the production orchestration middle is unbuilt.

## Distance to training

| Milestone | Work | Owner gates |
|---|---|---|
| M1 — traces under v3 | v3 packet, ruling, TDD implementation, regeneration | 1 |
| M2 — pilot corpus released *(training data ready)* | Todo 4 re-spec + selector round, 5 modules, ~3,100 renders for a 300-instance pilot | 2 |
| M3 — training starts | `planning_vlm/`: loader, env pinning, core, 2 backbone adapters, metrics, readiness | 0 |

Roughly **15–17 focused sessions and 3 owner rulings** at the observed rate of about one
substantial module per session. Pad it: this project has hit a hard blocker at nearly every todo
(Todo 4 infeasibility, the 2.25 TB trace explosion, the width defect, the `VIEW_ROOT` breakage).

**Training data ready is M2 — about two-thirds of the remaining distance.** M3 is smaller but
entirely greenfield.

## The lever worth deciding deliberately

Todos 5–10 exist to produce an **auditable production release** — review packet, two owner
checkpoints, atomic release with rollback. A **calibration pilot may need none of it**. The fixture
corpus was built without those modules.

If the pilot goes through the fixture path with lighter-weight selection, M2 drops from five modules
and two owner gates to roughly one module and none — **halving the distance to training data**.

The counter-argument is real and should be put to the owner rather than assumed away: the pilot's
output feeds a go/no-go gate (Gate 3), and a corpus built off the audited path carries weaker
provenance for a decision that kills or continues the method. The question is whether Gate 3 needs
release-grade provenance or only reproducibility.

## Related

- [[calibration-pilot-sizing]] — how big the pilot has to be, which interacts with this directly
- [[phase-a-width-escalation-result]] — what unblocked the corpus in the first place
