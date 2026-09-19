# Goal 11 terminal VALID_STOP report

## Decision

The `generalization_robustness` branch is terminal `VALID_STOP`. The qualified
suite cannot be evaluated within its frozen 32 GPU-h branch under the
Gate-2-confirmed admission rule. No derived-task model evaluation was
launched. Issues [#96](https://github.com/Sino-Huang/multimodality_on_planning/issues/96)
and [#98](https://github.com/Sino-Huang/multimodality_on_planning/issues/98)
remain OPEN.

- Branch: `generalization_robustness`, 32 GPU-h cap
- Protocol: `expanded-generalization-robustness-v1`
- Protocol SHA-256: `f8b83a701641799441c94391ca35ef355a940936db16b907aad7b3ea6bbb5ca0`
- Program: `expanded-nine-day-v1`
- GPU cutoff: `2026-09-21T11:55:19Z`
- Gate: Gate 2, `VALID_STOP-CONFIRMED`

This is a terminal evidence publication, not a ticket-completion claim. The
qualification and semantic-audit evidence are complete, but the execution
deliverable required by #96/#98 was not run.

## Qualification milestone

The frozen suite generated 120 variants: 24 scale-up, 24 shifted-init, and 72
perturbations. Qualification retained 93 eligible variants and reported 27
missing variants. There were zero replacements.

Missing coverage is exactly:

- 24 `exact_reference_failed:bfs:expansion_budget_exhausted` structural cases.
- 2 `initial_goal` cases: `visitall-shifted-init-940022` and
  `visitall-shifted-init-940023`.
- 1 structural whole-instance overlap:
  `ferry-shifted-init-940010`, caught by disjointness.

The eligible composition is 24 P1 object-renaming, 24 P2 render-restyle, 24
P3 name-compression, 6 scale-up, and 15 shifted-init variants. Structural
disjointness is `True` for all 21 eligible structural variants.

The frozen evidence hashes are:

- `suite.json`:
  `a20c30cc7b57a784e955626b07e4eea28a956964c300b6404467d956e092a742`
- `qualification.json`:
  `cb5badf72543e351fff2a822b0cf4e2fc3b754405f7ef1d1369118891921118f`

The compact published evidence is
[generalization-robustness-qualification.json](generalization-robustness-qualification.json)
(per-variant eligibility, reasons, measured classifications, reference decisions and
the evidence hashes above). Full artifacts (`suite.json`, `qualification.json`,
`probe.json`, per-candidate receipts) are preserved under
`outputs/expanded-study/v1/generalization-robustness/` per the local outputs
convention and are identified by the sha256 values above; they are not copied into
git.

## Semantic classifications

Measured classification is authoritative over the frozen expected prior. The
audit definition is differential: an information item is lost only when it is
recoverable from the source view and not recoverable from the perturbed view.

- P1: 72/72 modality classifications semantics-preserving.
- P2: 72/72 modality classifications semantics-preserving. All 24 had
  `bytes_differ` and `visibility_preserved`; the frozen render override was
  `{canvas_size: 160, layout_offset: [-0.04, -0.04]}`.
- P3: text-state 24/24 lossy; visual-state 24/24 preserving; multimodal-state
  18 lossy and 6 preserving. The 18 multimodal losses are the 9 domains with
  non-injective source visual type content, times 2 variants. The text type
  annotations were stripped and the visual view provided no recoverable type
  backstop in those domains.

## Probe

The branch probe made 180 outcome-free timing calls: 60 combinations times 3
samples. It charged `0.6272556656599044` GPU-h on `generalization-probe`
attempt 1, using `MASTER_PORT=18800` and launch head
`1f4034d63fd1fb14e7bd15ae2ad5708241349135`.

The per-combination bounds are maximum observed call time multiplied by 1.5,
ranging from 15.98 s to 98.12 s. Worker overhead was 112.25 s, comprising
111.15 s model load and 1.11 s model save. Probe evidence is retained at
`outputs/expanded-study/v1/generalization-robustness/probe.json` and has
SHA-256:

`a198d8cefe5cb28b70a433fed64927972f179451e6c17cd54d37e10315ece18e`

The persist whitelist retained timing and token metadata only. No model
generation outputs or derived-task episode outcomes were retained by the
probe.

## Admission

Admission was ledger-read-only: `ledger_mutated=false`, with no transfer
executed and no evaluation launched.

| Scope label | Eligible-applied tasks | Required GPU-h | Fits 31.3727 GPU-h remainder |
| --- | ---: | ---: | --- |
| L0 | 93 | 3936.35 | No |
| L2 | 69 | 2907.40 | No |
| L3 | 34 | 1704.89 | No |

The exact evidence values are L0 `3936.346431476061`, L2
`2907.3974080484677`, and L3 `1704.8882762214641` GPU-h, against a branch
remainder of `31.372744334340094` GPU-h and `24.0` GPU-h recovery available.
The admission decision is L4, outcome `VALID_STOP`, with
`transfer_request: null`.

The L0/L2/L3 labels are declared scope labels, not the post-screening task
counts: they refer to declared 120/96/48 scopes, while the arithmetic applies
to the eligible 93/69/34 tasks remaining after the 27 exclusions. This is the
oracle-recorded label distinction. Two immaterial arithmetic nits remain
recorded: protocol formula order versus code differs by 0.0156 GPU-h, and
probe spend is conservatively double-counted by 0.63 GPU-h.

The bound stands as a completion-reservation bound. Every model condition is
priced through its runtime-enforced 2x decision-call cap at the slowest
qualified call bound, with the safety factor applied. The bound was frozen
before any derived-task outcome and Gate 2 confirmed it as legitimate. The
baseline's realized behavior was approximately 36.2 s per episode, roughly
36-40 s under those conditions, but it included early invalid termination and
cannot guarantee completion on the harder shifted tasks. Partial coverage
cannot satisfy the gate. Correcting the model solely to obtain a runnable scope
would be goalpost-moving under the ruling.

## Measured alternatives

The declared fallback alternatives were measured for feasibility framing, not
executed:

- Structural-only: 21 tasks x 24 GPU episodes = 504 GPU episodes.
- Robustness fallback: 1 problem per domain x P1/P2/P3 = 36 tasks x 24 = 864
  GPU episodes.

The oracle's realistic-cost framing is approximately 62-124 GPU-h for the
full eligible matrix at a realistic 100-200 s per episode. The reduced scopes
still require a new versioned protocol and fresh design gate; they cannot close
#96/#98 under the current wording.

## Legitimate future path

A future run requires a new versioned protocol and admission artifact, an
independently justified runtime estimand frozen before recomputation, an
explicit equation and fallback membership frozen before recomputation, and
only existing timing, reference, or historical evidence. It must preserve the
93/27 qualification freeze, receive fresh design-gate ratification, and retain
the L4 result for the current protocol. Derived-task scores cannot be used to
select a new runnable scope.

## Budget accounting

The branch charged `0.6272556656599044` GPU-h, reported as 0.627256/32 GPU-h.
The pre-Goal-11 cumulative program sum was `40.06785503115919` GPU-h. The
program cumulative after the branch is:

`40.067855 + 0.627256 = 40.695111 / 336 GPU-h`.

No recovery transfer was executed.

## Defect-fix history

The qualification harness fixes addressed stale audit-receipt reuse, mapped
reference replay, semantic source ordering in the shared controller harness,
differential classification, source-qualified P2 scene graphs, declared
canvas-size handling, and the baseline-evidence write path. The baseline
published evidence is now read-only. The acid tests remained green after the
harness changes: curriculum `243/243` and baseline `1152/1152`.

## Evidence and validation

- Frozen protocol:
  `configs/experiments/expanded-study/generalization-robustness-protocol.json`
- Qualification source:
  `outputs/expanded-study/v1/generalization-robustness/qualification.json`
- Suite source:
  `outputs/expanded-study/v1/generalization-robustness/suite.json`
- Qualification hashes:
  `outputs/expanded-study/v1/generalization-robustness/suite-sha256.json`
- Probe source:
  `outputs/expanded-study/v1/generalization-robustness/probe.json`
- Admission source:
  `outputs/expanded-study/v1/generalization-robustness/admission.json`

The published JSON files were copied byte-for-byte from the qualification and
suite sources. `python3 -m json.tool` was run on both new JSON files;
`git diff --check` was run; the two acid commands printed their required PASS
lines; and the final targeted suites passed `76` tests with Ruff reporting
`All checks passed!`. The published baseline evidence hashes remained
`ba470dd4498e11a21fba8e9f61611c8f7be6ddcb167ad02a7fbed6e1516eb03a` and
`7f78b9d2cbda99446be52690b796975b77010522bd768c0d77cce6858cf4a366`.

No existing file was intentionally modified and no commit was created.
