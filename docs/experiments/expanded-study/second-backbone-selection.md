# Second-backbone selection — #101 (frozen before any backbone outcome)

Program: expanded-nine-day-v1. Branch: `second_backbone` (40 GPU-h of 336).
Prepared 2026-09-18, before any second-backbone probe, training, or evaluation result.

## Decision

**Selected backbone: `OpenGVLab/InternVL3_5-8B-HF`, revision
`741a7d03020411e666c6109218ab71e08151ef86`** (22 files, 16 GB, downloaded into the
project-local `HF_HOME` on 2026-09-18; all loads use `local_files_only=True`).

Selection used official capability/license documentation and measured local capacity
only. No final-test performance of any candidate was observed or used.

## Criteria and evidence

| Criterion | Evidence |
| --- | --- |
| Official capability | [Model card](https://huggingface.co/OpenGVLab/InternVL3_5-8B-HF): ViT–MLP–LLM (InternViT-300M + pixel-shuffle + Qwen3-8B), 8.5B parameters, SFT context 32K tokens, documented multimodal reasoning, OCR/document, GUI and embodied capability; HF-format checkpoints "fully consistent with the APIs of the official HuggingFace models". |
| License | Apache-2.0 (model card "License" section; Qwen3 component also Apache-2.0). Compatible with this MIT project's release. |
| Measured capacity | 8.5B params × 4 B (parity-safe float32) ≈ 34 GB weights; the primary backbone's measured fp32 peak on the same A100-80GB was 38.8 GB (`outputs/matched_modalities/v3/qualification/gpu-0.json`); GPU0/GPU1 had 71.6/79.6 GB free at branch start. Same size class as the primary; fits one worker per GPU. |
| Environment compatibility | Native `InternVLForConditionalGeneration`/`InternVLProcessor` in the frozen `transformers==4.57.0` (import-verified); `supports_gradient_checkpointing=True`; no `trust_remote_code`; no new packages. |
| Local executability | Weights verified on disk in the project HF cache; LLM context 40,960 positions ≥ the frozen 32,768 contract. |

## Candidates considered and rejected

| Candidate | Verdict | Documented reason (capability/license/capacity/environment) |
| --- | --- | --- |
| `allenai/Molmo2-8B` | Rejected | Official quick start pins `transformers==4.57.1` (env freeze has 4.57.0) and requires the extra `molmo_utils` package and `trust_remote_code=True`; card notes training data "subject to academic and non-commercial research use only". Environment/freeze and licensing posture risk. |
| `Qwen/Qwen2.5-VL-7B-Instruct` | Fallback only | Runs in the frozen env, but shares the primary backbone's vendor, interface paradigm and image-token scheme — the weakest architectural contrast. Retained as the predeclared fallback, usable only on a measured-capacity/probe failure of the primary selection (VALID_STOP of the primary pick), never on outcomes. |
| `google/gemma-4-E2B-it`, `Qwen/Qwen3.5-VL-4B`, `openbmb/MiniCPM-V-4.6` | Rejected | Require `transformers>=5.x`; incompatible with the frozen environment. |
| >13B-class VLMs | Rejected | Parity-safe float32 inference cannot fit one A100-80GB (measured primary profile: ~39 GB peak at 8.77B). |

## Disclosed architecture overlap

InternVL3.5-8B's language model is Qwen3-8B — the same LLM family as the primary
backbone's text tower. The replication contrast is therefore in the vision tower
(InternViT-300M vs Qwen3-VL ViT), the connector (pixel-shuffle vs patch-merge), the
image tokenization (fixed 256-token tiles at 448×448, dynamic tiling ≤12 + thumbnail
vs native-resolution grid), and the multimodal training recipe — not in the LLM
decoder family. This is reported as an architecture-scope limitation wherever
replication claims are made.

## Processor treatment (frozen; disclosed per #102 comment)

The pinned processor behavior is the official release behavior, unchanged
(`processor_overrides: {}`), symmetric with the v5 Qwen pin:

- The real call path forces `crop_to_patches=True`: dynamic 448×448 tiling
  (`min_patches=1`, `max_patches=12`, plus one thumbnail tile when tiled); each tile
  encodes as `<img>` + 256 × `<IMG_CONTEXT>` + `</img>`.
- Measured: 768×1024 page → 13 tiles = 3,330 tokens (primary: 768); 128×128 scene →
  1 tile = 258 tokens (primary: 16). Live/training inputs are therefore larger under
  this backbone; input qualification re-measures every input, and batching is
  qualified on those measurements before outcomes.
- Tokenizer is the Qwen3-family BPE (vocab 151,936); text-token identity with the
  primary tokenizer is verified per-record in input qualification.
- Processed-pixel previews are published with the qualification evidence.

## Qualification bound to this selection (pre-outcome)

1. Input qualification (CPU): every declared training/live input re-measured under
   the pinned processor; `verify_complete` cross-checks; VALID_STOP if any input
   plus 384 output tokens exceeds 32,768.
2. Hardware probes (GPU, #54 lessons): fp32 scalar-vs-batch byte parity,
   repeated-batch determinism, adapter isolation, model-load and lower-95%
   throughput at actual precision/batch settings, token-limit guard behavior.
3. Cost admission: measured costs × 1.25 safety must fit the 40 GPU-h branch
   remainder, else a documented reduced scope (selected by reference cost only) or
   VALID_STOP — never a silent reduction.

Frozen selection SHA-256 and qualification/probe results are published as
`second-backbone-qualification.json` / `second-backbone-probe.json` under
`outputs/expanded-study/v1/second-backbone/` and copied to this directory.
