# Transfer paired analysis (post-hoc, CPU-only)

Per-example McNemar exact tests of each adapted cell against the v1 base cell over the frozen
subsets (folio 200, gsm8k 200, humaneval 164). v2 extension cells pair against the same v1 base
predictions (byte-identical subsets). Holm correction across all 36 comparisons.
Exploratory: computed after observing outcomes; single training seed (17).

| Benchmark | Cell | base n correct | cell n correct | delta | base-only | cell-only | McNemar p | Holm p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| folio | bfs_text | 120 | 120 | +0 | 2 | 2 | 1.0000 | 1.0000 |
| folio | bfs_visual | 120 | 121 | +1 | 3 | 4 | 1.0000 | 1.0000 |
| folio | bfs_multimodal | 120 | 121 | +1 | 3 | 4 | 1.0000 | 1.0000 |
| folio | iw_text | 120 | 132 | +12 | 6 | 18 | 0.0227 | 0.8156 |
| folio | iw_visual | 120 | 129 | +9 | 6 | 15 | 0.0784 | 1.0000 |
| folio | iw_multimodal | 120 | 129 | +9 | 6 | 15 | 0.0784 | 1.0000 |
| folio | astar_w3_text | 120 | 118 | -2 | 6 | 4 | 0.7539 | 1.0000 |
| folio | astar_w3_visual | 120 | 115 | -5 | 8 | 3 | 0.2266 | 1.0000 |
| folio | astar_w3_multimodal | 120 | 118 | -2 | 5 | 3 | 0.7266 | 1.0000 |
| folio | astar_greedy_text | 120 | 118 | -2 | 6 | 4 | 0.7539 | 1.0000 |
| folio | astar_greedy_visual | 120 | 118 | -2 | 6 | 4 | 0.7539 | 1.0000 |
| folio | astar_greedy_multimodal | 120 | 118 | -2 | 6 | 4 | 0.7539 | 1.0000 |
| gsm8k | bfs_text | 191 | 190 | -1 | 5 | 4 | 1.0000 | 1.0000 |
| gsm8k | bfs_visual | 191 | 189 | -2 | 5 | 3 | 0.7266 | 1.0000 |
| gsm8k | bfs_multimodal | 191 | 193 | +2 | 3 | 5 | 0.7266 | 1.0000 |
| gsm8k | iw_text | 191 | 192 | +1 | 2 | 3 | 1.0000 | 1.0000 |
| gsm8k | iw_visual | 191 | 193 | +2 | 3 | 5 | 0.7266 | 1.0000 |
| gsm8k | iw_multimodal | 191 | 192 | +1 | 3 | 4 | 1.0000 | 1.0000 |
| gsm8k | astar_w3_text | 191 | 190 | -1 | 4 | 3 | 1.0000 | 1.0000 |
| gsm8k | astar_w3_visual | 191 | 193 | +2 | 0 | 2 | 0.5000 | 1.0000 |
| gsm8k | astar_w3_multimodal | 191 | 189 | -2 | 3 | 1 | 0.6250 | 1.0000 |
| gsm8k | astar_greedy_text | 191 | 190 | -1 | 4 | 3 | 1.0000 | 1.0000 |
| gsm8k | astar_greedy_visual | 191 | 191 | +0 | 3 | 3 | 1.0000 | 1.0000 |
| gsm8k | astar_greedy_multimodal | 191 | 190 | -1 | 2 | 1 | 1.0000 | 1.0000 |
| humaneval | bfs_text | 128 | 130 | +2 | 4 | 6 | 0.7539 | 1.0000 |
| humaneval | bfs_visual | 128 | 131 | +3 | 5 | 8 | 0.5811 | 1.0000 |
| humaneval | bfs_multimodal | 128 | 128 | +0 | 4 | 4 | 1.0000 | 1.0000 |
| humaneval | iw_text | 128 | 126 | -2 | 6 | 4 | 0.7539 | 1.0000 |
| humaneval | iw_visual | 128 | 125 | -3 | 5 | 2 | 0.4531 | 1.0000 |
| humaneval | iw_multimodal | 128 | 124 | -4 | 6 | 2 | 0.2891 | 1.0000 |
| humaneval | astar_w3_text | 128 | 134 | +6 | 1 | 7 | 0.0703 | 1.0000 |
| humaneval | astar_w3_visual | 128 | 131 | +3 | 3 | 6 | 0.5078 | 1.0000 |
| humaneval | astar_w3_multimodal | 128 | 127 | -1 | 3 | 2 | 1.0000 | 1.0000 |
| humaneval | astar_greedy_text | 128 | 131 | +3 | 4 | 7 | 0.5488 | 1.0000 |
| humaneval | astar_greedy_visual | 128 | 133 | +5 | 2 | 7 | 0.1797 | 1.0000 |
| humaneval | astar_greedy_multimodal | 128 | 130 | +2 | 3 | 5 | 0.7266 | 1.0000 |

Smallest raw p 0.0227; smallest Holm-adjusted p 0.8156.
No comparison reaches significance after Holm correction.

Machine-readable evidence: [transfer-paired-analysis.json](transfer-paired-analysis.json).
