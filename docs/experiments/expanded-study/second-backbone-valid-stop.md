# Second-backbone terminal VALID_STOP (#101-#103)

The `second_backbone` branch is terminal **VALID_STOP** at the frozen cost-admission gate (decision **L2**). No adapter training and no panel evaluation were launched; the only GPU work was the outcome-blind runtime probe plus one determinism debug job, while input qualification ran CPU-only. This is a terminal evidence publication, not a ticket-completion claim.

- Branch: `second_backbone`, 40 GPU-h cap; spent 3.9577; remainder 36.0423.
- Protocol: `expanded-second-backbone-v1` (`configs/experiments/expanded-study/second-backbone-protocol.json`).
- Backbone: `OpenGVLab/InternVL3_5-8B-HF` @ `741a7d03020411e666c6109218ab71e08151ef86`.
- GPU cutoff: `2026-09-21T11:55:19Z`; ledger mutated by admission: False.

## Admission arithmetic

Basis: 2 x reference bfs decisions per task (the frozen decision-call allowance); measured probe p95 per-call latency and measured training-step wall times, times safety factor 1.25.

| Level | Episodes | Train GPU-h | Eval GPU-h | Required incl. spent | Fits remainder |
| --- | ---: | ---: | ---: | ---: | --- |
| L0 | 144 | 2.70 | 200.87 | 258.42 | False |
| L1 | 72 | 2.70 | 32.64 | 48.14 | False |

Even the reference-cost-only reduced key-cell panel (L1: lowest reference BFS decision counts, frozen before any model outcome) exceeds the branch remainder, so the frozen rule returns L2 / VALID_STOP. The bound prices every model-condition episode at the slowest measured p95 call for its full 2x reference decision-call allowance; realized episodes can terminate earlier, but partial coverage cannot satisfy the gate and relaxing the bound to obtain a runnable scope would be goalpost-moving.

## Qualification milestone (#101, fulfilled)

Input qualification **PASS** (complete: True): 1536 training records, 24 panel tasks and 5907 reference decisions measured; tokenizer identity with the Qwen templated ids: True; violations: 0.

See [second-backbone-qualification.md](second-backbone-qualification.md).

## Probe milestone (outcome-blind runtime gates, all PASS)

Probe **PASS** after 5 scheduler attempts (1.31 GPU-h on the final successful attempt): scalar/batch byte parity True, repeated-batch determinism True, adapter isolation (disable restores base: True), token-limit guards (near-limit 17514 tokens succeeded; oversize batch raises VALID_STOP), attention applied `visual_sdpa` with fallback used: False.

See [second-backbone-probe.md](second-backbone-probe.md).

## Issue disposition

- #101 (qualify and pin the second backbone): fulfilled by the pinned backbone, the complete PASS qualification and the adapter-interface probe evidence above.
- #102 (train matched-exposure cells) and #103 (evaluate and verify): not executed; the frozen admission rule produced this certified no-run instead. Both issues remain OPEN.

## Budget accounting

The branch charged 3.9577 GPU-h of its 40 GPU-h cap (qualification 0; probe attempts and one determinism debug job). Program cumulative after this branch: 44.6528 / 336 GPU-h.

## Legitimate future path

Any future run needs a new versioned protocol and admission artifact with a budget that fits the measured costs above, keeping the reference-cost-only reduced-scope rule frozen before any model outcome. No second-backbone model outcomes exist, so none can select a future scope.

Compact evidence: [second-backbone-admission.json](second-backbone-admission.json), [second-backbone-probe.json](second-backbone-probe.json) and [second-backbone-qualification.json](second-backbone-qualification.json) (byte-identical copies).
