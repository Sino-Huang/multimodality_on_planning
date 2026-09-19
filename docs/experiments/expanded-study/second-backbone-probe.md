# Second-backbone probe and admission (#101-#103)

Second-backbone probe and admission for `expanded-second-backbone-v2`.

Probe outcome: **PASS**; admission decision: **L1** (PASS).

- Attention: requested `visual_sdpa`, applied `visual_sdpa`, fallback used: False.
- Load: 34.1s; VRAM after load 34113274368 bytes.
- Scalar/batch byte parity: True; repeated-batch determinism: True.
- Adapter isolation: base≠A True, base≠B True, A≠B True, disable restores base True.
- Token-limit guards: near-limit (17514 tokens) succeeded True; oversize batch VALID_STOP True.

| Modality | Calls | Latency p50 (s) | Latency p95 (s) | Tokens/s (mean) | Peak VRAM (bytes) |
| --- | ---: | ---: | ---: | ---: | ---: |
| text-state | 20 | 31.80 | 32.39 | 8.2 | 37860141568 |
| visual-state | 20 | 64.75 | 71.68 | 4.2 | 42500715520 |
| multimodal-state | 20 | 71.12 | 79.55 | 3.8 | 43392428544 |

| Modality | One-step wall (s) | Microbatches | Peak VRAM (bytes) |
| --- | ---: | ---: | ---: |
| text-state | 46.1 | 32 | 23604285952 |
| visual-state | 268.3 | 32 | 45345070080 |
| multimodal-state | 293.5 | 32 | 47505704960 |

| Level | Episodes | Required GPU-h (incl. spent, x safety) | Fits remainder |
| --- | ---: | ---: | --- |
| L0 | 144 | 258.419 | False |
| L1 | 72 | 48.141 | True |

Branch cap 52.11 GPU-h; spent 3.958; remainder 48.152; ledger mutated: False.

Compact evidence: [second-backbone-probe.json](second-backbone-probe.json) and [second-backbone-admission.json](second-backbone-admission.json) (byte-identical copies).
