# Second-backbone v2 reduced-scope design (#123)

The `second_backbone` branch terminated **VALID_STOP** at the v1 cost-admission gate (decision L2; see [second-backbone-valid-stop.md](second-backbone-valid-stop.md)). This document freezes the prospective recovery: protocol `expanded-second-backbone-v2` (`configs/experiments/expanded-study/second-backbone-protocol-v2.json`) re-runs the branch at the frozen **L1 key-cell panel** (72 model episodes) under the amended 52.11 GPU-h cap. It supersedes nothing about the v1 evidence: the v1 VALID_STOP artifacts stay untouched under `outputs/expanded-study/v1/second-backbone`, and v2 writes only under the new root `outputs/expanded-study/v1/second-backbone-v2`.

- Branch: `second_backbone`; cap **52.11 GPU-h** (amended); spent **3.9577**; remainder **48.1523**.
- Status: `frozen_before_training` on 2026-09-19 — the same frozen-before-any-model-outcome semantics as v1's `frozen_before_qualification`, restated for a protocol whose qualification is already complete and reused.
- `issues: [123]`; `supersedes_not: [102, 103]`.
- Backbone unchanged: `OpenGVLab/InternVL3_5-8B-HF` @ `741a7d03020411e666c6109218ab71e08151ef86`.

## Scope: the frozen L1 key-cell membership

Rule (frozen before any model outcome, identical to the L1 fallback inside `decide_admission`): rank the 24 `expanded-panel-v2-qualified` tasks by `reference_costs.bfs.decisions` from `configs/experiments/expanded-study/final-panel.json` and keep the cheapest 12. Episodes = 12 tasks x 3 modalities x 2 model conditions = **72 model episodes**; **72 comparator episodes** (`random_valid`, `exact_reference`) are reused from the verified baseline evidence per the protocol's `evaluation.comparator_audit` block, never regenerated.

The 12 task_ids (frozen panel order; canonical-JSON sha256 `sha256:c65dbb70699752d2056b3b203e83f7b055d9811992b1e8630c4a73a72ad8c3f9`):

1. `expanded-final/15puzzle-compact-910000`
2. `expanded-final/depot-compact-912000`
3. `expanded-final/depot-expanded-912100`
4. `expanded-final/elevators-compact-914002`
5. `expanded-final/elevators-expanded-914105`
6. `expanded-final/ferry-compact-915000`
7. `expanded-final/ferry-expanded-915109`
8. `expanded-final/grid-compact-916000`
9. `expanded-final/logistics-compact-918000`
10. `expanded-final/logistics-expanded-918100`
11. `expanded-final/storage-compact-919000`
12. `expanded-final/towers_of_hanoi-compact-920000`

Dropped relative to L0 (reference BFS decisions): the 12 most expensive tasks, from `driverlog-expanded-913103` (94) up to `visitall-expanded-921100` (225).

## Admission arithmetic

Basis unchanged from v1: 2 x reference bfs decisions per task (the frozen decision-call allowance); measured probe p95 per-call latency and measured training-step wall times; safety factor 1.25; the conservative `required_including_spent <= branch remainder` comparison. All measured inputs are the v1 probe/qualification values, reused unchanged.

| Level | Episodes | Train GPU-h | Eval GPU-h | Safety | Required incl. spent | Fits remainder (48.1523) |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| L0 | 144 | 2.70 | 200.87 | 1.25 | 258.42 | False |
| L1 | 72 | 2.70 | 32.64 | 1.25 | 48.14 | **True** |

- Cap: **52.11**; spent: **3.957651311026679**; remainder: **48.15234868897332** GPU-h.
- L1 required including spent: **48.14088442694189** GPU-h; headroom **0.0115** GPU-h.
- Admission: `outputs/expanded-study/v1/second-backbone-v2/admission.json`, decision **L1**, outcome **PASS**, `ledger_mutated: false`.
- Computed by `scripts/qualify_expanded_second_backbone_v2.py`, which reuses the frozen `decide_admission` formula with the v2 protocol, the v1 qualification/probe artifacts, and the live ledger spend; the CLI `admit` stage remains v1-frozen (`validate_protocol` pins the v1 protocol identity and pre-transfer ledger). `require_admission_gate(ROOT, v2_protocol)` dry-run: PASS.

## Budget transfer record

The cap amendment is the prospective transfer already recorded in `outputs/expanded-study/v1/budget.json`:

- `transfers[0]`: source `recovery_reserve` -> target `second_backbone`, **12.11 GPU-h**, ratified by the user on 2026-09-19 (`source_committed_hours: 0`, i.e. nothing had been charged against the reserve).
- `allocations_gpu_hours`: `second_backbone` 40 -> **52.11**, `recovery_reserve` 24 -> **11.89**.
- The 336 GPU-h program total and the `2026-09-21T11:55:19Z` cutoff are unchanged; the transfer is prospective (documented before v2 execution), per the ledger's transfer policy.

## Prior-evidence reuse justification

The v1 qualification (`outputs/expanded-study/v1/second-backbone/qualification/qualification.json`, sha256 `sha256:c92069e28c1e4affe1d65daf9ecc258d58b7f4168c41fdafdc1a5a665ee29042`) and probe (`outputs/expanded-study/v1/second-backbone/probe.json`, sha256 `sha256:e089ccad94558ea68aa41a5cd775eb5d35efa9e6fb6668a1fdef3b4212da6ca3`) are reused **unchanged**, pinned by sha256 in the protocol's `prior_evidence_reuse` block. This is sound because:

1. **No model outcomes**: neither artifact contains any training or evaluation result — the qualification measures input records, views and reference decisions; the probe measures load, throughput, latency, determinism and token-limit guards. The branch has trained nothing and evaluated nothing.
2. **Nothing they measure has changed**: same backbone, revision, hardware, views contract, panel, seed and training configuration (the v2 `training` block is value-identical to v1).
3. The v2 admission script verifies both sha256 pins and the PASS/complete outcomes before computing, so any drift in the reused artifacts fails closed.

## What v2 does and does not settle

- v2 authorizes exactly one thing: the L1 reduced-scope run (train 3 matched-exposure cells, then evaluate the 12-task panel) under ticket **#123**.
- v2 **cannot close #102 or #103**. Those tickets cover the full matched-exposure cells and panel evaluation defined by the v1 protocol; the v1 admission returned L2/VALID_STOP and that evidence stands. #102/#103 remain OPEN; `supersedes_not: [102, 103]` is recorded in the protocol.
- **No second-backbone model outcomes existed before this freeze**; the L1 membership was selected by reference costs only, frozen before any model outcome, so the reduced scope cannot be an outcome-selected scope.
