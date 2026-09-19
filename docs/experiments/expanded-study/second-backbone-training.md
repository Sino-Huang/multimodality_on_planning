# Second-backbone training (#102)

Second-backbone training for `expanded-second-backbone-v2` trained three fresh InternVL LoRA adapters (one per modality) from the frozen base model.

Outcome: **PASS**. Fresh seed-17 LoRA initialization identical across cells: True (`sha256:9530a9ed1578c…`, 504 tensors).

| Modality | Records | Updates | Tensors changed | Final checkpoint sha256 |
| --- | ---: | ---: | ---: | --- |
| text-state | 512 | 16 | 504/504 | sha256:8c10e971a9773… |
| visual-state | 512 | 16 | 504/504 | sha256:23add6d32a07f… |
| multimodal-state | 512 | 16 | 504/504 | sha256:54ebbde85ac98… |

Every cell: same 512 BFS membership records in frozen membership order, one epoch, global batch 32 (microbatch 1 x accumulation 32), exactly 16 optimizer updates, sequential sampler, trainer reshuffling disabled, final checkpoint only, vision tower and multi-modal projector frozen.

Compact evidence: [second-backbone-training.json](second-backbone-training.json) (byte-identical copy of the runtime aggregate report).
