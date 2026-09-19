# Second-backbone analysis (#103)

Second-backbone paired whole-instance analysis for `expanded-second-backbone-v2` (12 paired units; bootstrap seed 1729, 10000 resamples, 0.95 confidence).

Success = goal reached with algorithm invariants holding. Intervals are paired bootstrap success-rate differences in proportion units.

| Modality | Contrast | Point | Lower | Upper |
| --- | --- | ---: | ---: | ---: |
| text-state | process_sft_minus_pretrained_base | 0.000 | 0.000 | 0.000 |
| text-state | process_sft_minus_random_valid | -0.750 | -1.000 | -0.500 |
| visual-state | process_sft_minus_pretrained_base | 0.000 | 0.000 | 0.000 |
| visual-state | process_sft_minus_random_valid | -0.750 | -1.000 | -0.500 |
| multimodal-state | process_sft_minus_pretrained_base | 0.000 | 0.000 | 0.000 |
| multimodal-state | process_sft_minus_random_valid | -0.750 | -1.000 | -0.500 |
| text-state | internvl3_5-8b_process_sft_minus_qwen3-vl-8b_process_sft | 0.000 | 0.000 | 0.000 |
| visual-state | internvl3_5-8b_process_sft_minus_qwen3-vl-8b_process_sft | 0.000 | 0.000 | 0.000 |
| multimodal-state | internvl3_5-8b_process_sft_minus_qwen3-vl-8b_process_sft | 0.000 | 0.000 | 0.000 |

Single-training-seed limitation: exactly one training run per cell; no training-seed variance is estimated or claimed.
Random-valid assistance: oracle-assisted valid-operation control; not equally assisted learned generation.
Architecture note: InternVL3.5-8B shares the Qwen3-8B LLM family with the primary backbone; the replication contrast is the vision tower (InternViT vs Qwen-ViT), connector, image tokenization, and multimodal training recipe, and it is reported as an architecture-difference limitation.

Compact evidence: [second-backbone-analysis.json](second-backbone-analysis.json) (byte-identical copy of the runtime analysis).
