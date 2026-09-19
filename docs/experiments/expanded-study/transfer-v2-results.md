# Transfer extension results (#104-#107)

Zero-shot transfer of the remaining planning-trained adapters for `transfer-extension-remaining-algorithms-v2` (admission decision **L0**), extending `transfer-folio-humaneval-gsm8k-v1`.

Cells: `iw_text`, `iw_visual`, `iw_multimodal`, `astar_w3_text`, `astar_w3_visual`, `astar_w3_multimodal`, `astar_greedy_text`, `astar_greedy_visual`, `astar_greedy_multimodal`. The base cell was already run under v1 and is not rerun; v1 base values are referenced where the admission levels match. Greedy decoding, seed 17, fp32; per-benchmark max_new_tokens folio 64 / gsm8k 512 / humaneval 768.

## Extension provenance

The v1 protocol declared base + three BFS-adapter cells and is complete. The user then explicitly requested testing the remaining nine trained adapters (best_first_width, best_first_add_w3, best_first_add_greedy x text/visual/multimodal). This extension is exhaustive over every remaining verified trained cell — it does not select adapters by observed transfer success — and reuses the v1 frozen subsets, prompts, decoding, parsing, sandbox and metrics unchanged. It was authorized after the v1 BFS transfer results were observed; that timing is disclosed here and in the published narrative.

- Extension timing: this extension was authorized **after** the v1 BFS transfer results were observed; it is exhaustive over every remaining verified trained cell, so it does not select adapters by observed transfer success.
- v1 base/BFS evidence: [transfer-results.md](transfer-results.md); v1 evidence is never overwritten.

## Frozen subsets

| Benchmark | L0 | L1 | Strata | L0 order sha256 |
| --- | ---: | ---: | --- | --- |
| folio | 200 | 100 | {"False": 62, "True": 70, "Uncertain": 68} | `sha256:f0225ae2fea29…` |
| gsm8k | 200 | 100 | {"q0": 50, "q1": 50, "q2": 50, "q3": 50} | `sha256:1a7b26c5dac44…` |
| humaneval | 164 | 82 | {} | `sha256:2fc7921d5d834…` |

Subsets are the v1 frozen subsets reused byte-identically (sha256 `24157aaadc6f3c2b1bf7ff1e858a3a7bef93f98f68354d8d1334b30bfaa12627`), verified at freeze; no re-selection and no re-derivation.

## Results

| Benchmark | Cell | Examples | Correct | Accuracy/pass@1 | Malformed | Categories |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| folio | base (v1 reference) | 200 | 120 | 0.6000 | 0 | {"correct": 120, "incorrect": 80} |
| folio | iw_text | 200 | 132 | 0.6600 | 0 | {"correct": 132, "incorrect": 68} |
| folio | iw_visual | 200 | 129 | 0.6450 | 0 | {"correct": 129, "incorrect": 71} |
| folio | iw_multimodal | 200 | 129 | 0.6450 | 0 | {"correct": 129, "incorrect": 71} |
| folio | astar_w3_text | 200 | 118 | 0.5900 | 0 | {"correct": 118, "incorrect": 82} |
| folio | astar_w3_visual | 200 | 115 | 0.5750 | 0 | {"correct": 115, "incorrect": 85} |
| folio | astar_w3_multimodal | 200 | 118 | 0.5900 | 0 | {"correct": 118, "incorrect": 82} |
| folio | astar_greedy_text | 200 | 118 | 0.5900 | 0 | {"correct": 118, "incorrect": 82} |
| folio | astar_greedy_visual | 200 | 118 | 0.5900 | 0 | {"correct": 118, "incorrect": 82} |
| folio | astar_greedy_multimodal | 200 | 118 | 0.5900 | 0 | {"correct": 118, "incorrect": 82} |
| gsm8k | base (v1 reference) | 200 | 191 | 0.9550 | 0 | {"correct": 191, "incorrect": 9} |
| gsm8k | iw_text | 200 | 192 | 0.9600 | 0 | {"correct": 192, "incorrect": 8} |
| gsm8k | iw_visual | 200 | 193 | 0.9650 | 0 | {"correct": 193, "incorrect": 7} |
| gsm8k | iw_multimodal | 200 | 192 | 0.9600 | 0 | {"correct": 192, "incorrect": 8} |
| gsm8k | astar_w3_text | 200 | 190 | 0.9500 | 0 | {"correct": 190, "incorrect": 10} |
| gsm8k | astar_w3_visual | 200 | 193 | 0.9650 | 0 | {"correct": 193, "incorrect": 7} |
| gsm8k | astar_w3_multimodal | 200 | 189 | 0.9450 | 0 | {"correct": 189, "incorrect": 11} |
| gsm8k | astar_greedy_text | 200 | 190 | 0.9500 | 0 | {"correct": 190, "incorrect": 10} |
| gsm8k | astar_greedy_visual | 200 | 191 | 0.9550 | 0 | {"correct": 191, "incorrect": 9} |
| gsm8k | astar_greedy_multimodal | 200 | 190 | 0.9500 | 0 | {"correct": 190, "incorrect": 10} |
| humaneval | base (v1 reference) | 164 | 128 | 0.7805 | 2 | {"malformed": 2, "passed": 128, "runtime_error": 12, "wrong_answer": 22} |
| humaneval | iw_text | 164 | 126 | 0.7683 | 2 | {"malformed": 2, "passed": 126, "runtime_error": 15, "wrong_answer": 21} |
| humaneval | iw_visual | 164 | 125 | 0.7622 | 1 | {"malformed": 1, "passed": 125, "runtime_error": 15, "wrong_answer": 23} |
| humaneval | iw_multimodal | 164 | 124 | 0.7561 | 2 | {"malformed": 2, "passed": 124, "runtime_error": 14, "wrong_answer": 24} |
| humaneval | astar_w3_text | 164 | 134 | 0.8171 | 5 | {"malformed": 5, "passed": 134, "runtime_error": 8, "wrong_answer": 17} |
| humaneval | astar_w3_visual | 164 | 131 | 0.7988 | 2 | {"malformed": 2, "passed": 131, "runtime_error": 7, "wrong_answer": 24} |
| humaneval | astar_w3_multimodal | 164 | 127 | 0.7744 | 2 | {"malformed": 2, "passed": 127, "runtime_error": 10, "wrong_answer": 25} |
| humaneval | astar_greedy_text | 164 | 131 | 0.7988 | 6 | {"malformed": 6, "passed": 131, "runtime_error": 9, "wrong_answer": 18} |
| humaneval | astar_greedy_visual | 164 | 133 | 0.8110 | 2 | {"malformed": 2, "passed": 133, "runtime_error": 7, "wrong_answer": 22} |
| humaneval | astar_greedy_multimodal | 164 | 130 | 0.7927 | 2 | {"malformed": 2, "passed": 130, "runtime_error": 9, "wrong_answer": 23} |

## Costs

| Benchmark | Cell | Generated tokens | Input tokens | Latency (s) |
| --- | --- | ---: | ---: | ---: |
| folio | iw_text | 247 | 28680 | 41.1 |
| folio | iw_visual | 249 | 28680 | 40.1 |
| folio | iw_multimodal | 248 | 28680 | 40.8 |
| folio | astar_w3_text | 268 | 28680 | 40.8 |
| folio | astar_w3_visual | 280 | 28680 | 40.8 |
| folio | astar_w3_multimodal | 280 | 28680 | 41.0 |
| folio | astar_greedy_text | 267 | 28680 | 40.9 |
| folio | astar_greedy_visual | 276 | 28680 | 41.2 |
| folio | astar_greedy_multimodal | 278 | 28680 | 41.6 |
| gsm8k | iw_text | 28399 | 23975 | 495.6 |
| gsm8k | iw_visual | 28186 | 23975 | 452.0 |
| gsm8k | iw_multimodal | 28027 | 23975 | 461.7 |
| gsm8k | astar_w3_text | 29760 | 23975 | 495.2 |
| gsm8k | astar_w3_visual | 30300 | 23975 | 515.4 |
| gsm8k | astar_w3_multimodal | 30774 | 23975 | 528.7 |
| gsm8k | astar_greedy_text | 29466 | 23975 | 481.7 |
| gsm8k | astar_greedy_visual | 30199 | 23975 | 521.6 |
| gsm8k | astar_greedy_multimodal | 30798 | 23975 | 530.5 |
| humaneval | iw_text | 14022 | 29393 | 336.0 |
| humaneval | iw_visual | 14058 | 29393 | 313.0 |
| humaneval | iw_multimodal | 14143 | 29393 | 328.6 |
| humaneval | astar_w3_text | 15598 | 29393 | 338.7 |
| humaneval | astar_w3_visual | 15723 | 29393 | 341.9 |
| humaneval | astar_w3_multimodal | 14259 | 29393 | 309.5 |
| humaneval | astar_greedy_text | 15855 | 29393 | 398.3 |
| humaneval | astar_greedy_visual | 15230 | 29393 | 313.5 |
| humaneval | astar_greedy_multimodal | 14403 | 29393 | 337.1 |

Admission measured probe inputs: {"folio": 0.37637347597628834, "gsm8k": 6.332932984083891, "humaneval": 6.666354911588132} seconds/example p95; model load 46.4s; probe 0.320 GPU-h.

## Missingness

Missing (benchmark, cell) coverage: []. Scores outcome: PASS; final report outcome: PASS.

## Leakage check

Normalized-token 8-gram containment of every frozen benchmark input against the full issue74-matched-32k-v1 SFT corpus (76217 records): **7** benchmark items share an 8-gram (details in leakage.json).

## Limitations

- Single decoding seed (17); no variance estimated.
- Qwen3-VL-8B-Instruct pretraining data is not auditable by this project; possible base-model benchmark contamination is disclosed, not measured.
- FOLIO is the v0.0 validation split (the official public evaluation set; test labels unreleased), not the access-gated HF yale-nlp/FOLIO v2 update.
- This extension was authorized after the v1 BFS transfer results were observed; the timing is disclosed in Extension provenance and contrasts reference the v1 base cell.

Compact evidence: [transfer-v2-protocol-checks.json](transfer-v2-protocol-checks.json), [transfer-v2-admission.json](transfer-v2-admission.json), [transfer-v2-scores.json](transfer-v2-scores.json) and [transfer-v2-final-report.json](transfer-v2-final-report.json) (byte-identical copies).
