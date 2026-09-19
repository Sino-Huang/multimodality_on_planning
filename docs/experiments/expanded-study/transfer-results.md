# Transfer benchmark results (#104-#107)

Zero-shot transfer of planning-trained BFS LoRA adapters for `transfer-folio-humaneval-gsm8k-v1` (admission decision **L0**).

Cells: base Qwen3-VL-8B-Instruct plus the `bfs_text`, `bfs_visual` and `bfs_multimodal` adapters; greedy decoding, seed 17, fp32; per-benchmark max_new_tokens folio 64 / gsm8k 512 / humaneval 768.

## Frozen subsets

| Benchmark | L0 | L1 | Strata | L0 order sha256 |
| --- | ---: | ---: | --- | --- |
| folio | 200 | 100 | {"False": 62, "True": 70, "Uncertain": 68} | `sha256:f0225ae2fea29…` |
| gsm8k | 200 | 100 | {"q0": 50, "q1": 50, "q2": 50, "q3": 50} | `sha256:1a7b26c5dac44…` |
| humaneval | 164 | 82 | {} | `sha256:2fc7921d5d834…` |

Subset selection used label strata (folio), reasoning-step quartiles (gsm8k) and full coverage (humaneval) only — never model outcomes. L1 is the even-numbered positions of each frozen L0 order.

## Results

| Benchmark | Cell | Examples | Correct | Accuracy/pass@1 | Malformed | Categories |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| folio | base | 200 | 120 | 0.6000 | 0 | {"correct": 120, "incorrect": 80} |
| folio | bfs_text | 200 | 120 | 0.6000 | 0 | {"correct": 120, "incorrect": 80} |
| folio | bfs_visual | 200 | 121 | 0.6050 | 0 | {"correct": 121, "incorrect": 79} |
| folio | bfs_multimodal | 200 | 121 | 0.6050 | 0 | {"correct": 121, "incorrect": 79} |
| gsm8k | base | 200 | 191 | 0.9550 | 0 | {"correct": 191, "incorrect": 9} |
| gsm8k | bfs_text | 200 | 190 | 0.9500 | 0 | {"correct": 190, "incorrect": 10} |
| gsm8k | bfs_visual | 200 | 189 | 0.9450 | 0 | {"correct": 189, "incorrect": 11} |
| gsm8k | bfs_multimodal | 200 | 193 | 0.9650 | 0 | {"correct": 193, "incorrect": 7} |
| humaneval | base | 164 | 128 | 0.7805 | 2 | {"malformed": 2, "passed": 128, "runtime_error": 12, "wrong_answer": 22} |
| humaneval | bfs_text | 164 | 130 | 0.7927 | 1 | {"malformed": 1, "passed": 130, "runtime_error": 11, "wrong_answer": 22} |
| humaneval | bfs_visual | 164 | 131 | 0.7988 | 0 | {"passed": 131, "runtime_error": 9, "wrong_answer": 24} |
| humaneval | bfs_multimodal | 164 | 128 | 0.7805 | 1 | {"malformed": 1, "passed": 128, "runtime_error": 10, "wrong_answer": 25} |

## Costs

| Benchmark | Cell | Generated tokens | Input tokens | Latency (s) |
| --- | --- | ---: | ---: | ---: |
| folio | base | 274 | 28680 | 35.2 |
| folio | bfs_text | 272 | 28680 | 40.4 |
| folio | bfs_visual | 275 | 28680 | 39.8 |
| folio | bfs_multimodal | 276 | 28680 | 40.1 |
| gsm8k | base | 29578 | 23975 | 428.8 |
| gsm8k | bfs_text | 27539 | 23975 | 443.0 |
| gsm8k | bfs_visual | 28211 | 23975 | 503.2 |
| gsm8k | bfs_multimodal | 27382 | 23975 | 458.8 |
| humaneval | base | 14146 | 29393 | 294.4 |
| humaneval | bfs_text | 13970 | 29393 | 304.9 |
| humaneval | bfs_visual | 13659 | 29393 | 304.4 |
| humaneval | bfs_multimodal | 13860 | 29393 | 296.6 |

Admission measured probe inputs: {"folio": 0.3554461393505335, "gsm8k": 6.169090545736253, "humaneval": 5.50811470495537} seconds/example p95; model load 43.2s; probe 0.126 GPU-h.

## Missingness

Missing (benchmark, cell) coverage: []. Scores outcome: PASS; final report outcome: PASS.

## Leakage check

Normalized-token 8-gram containment of every frozen benchmark input against the full issue74-matched-32k-v1 SFT corpus (76217 records): **7** benchmark items share an 8-gram (details in leakage.json).

## Limitations

- Single decoding seed (17); no variance estimated.
- Qwen3-VL-8B-Instruct pretraining data is not auditable by this project; possible base-model benchmark contamination is disclosed, not measured.
- FOLIO is the v0.0 validation split (the official public evaluation set; test labels unreleased), not the access-gated HF yale-nlp/FOLIO v2 update.

Compact evidence: [transfer-protocol-checks.json](transfer-protocol-checks.json), [transfer-admission.json](transfer-admission.json), [transfer-scores.json](transfer-scores.json) and [transfer-final-report.json](transfer-final-report.json) (byte-identical copies).
