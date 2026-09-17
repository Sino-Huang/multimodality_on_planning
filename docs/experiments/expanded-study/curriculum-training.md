# Curriculum-by-modality training closeout (#119, Goal 10 Phase 2)

Goal 10 Phase 2 trained the frozen nine-cell curriculum matrix through the
shared scheduler and independently verified every checkpoint. Each cell is a
fresh LoRA adapter trained from the base model (Qwen/Qwen3-VL-8B-Instruct,
revision 0c351dd01ed87e9c1b53cbc748cba10e6187ff3b — no starting checkpoint,
no historical checkpoint reuse) on the same 512 unique
`best_first_add_greedy` records from
`configs/experiments/matched-modalities/membership.json`, rendered through the
original v5 corpus path with identical targets. Per cell: one epoch, global
batch 32, exactly 16 optimizer updates, seed 17, sequential sampler over the
protocol-frozen ordering, trainer reshuffling disabled, final checkpoint only.

Compact evidence: [curriculum-training.json](curriculum-training.json)
(byte-identical copy of the runtime aggregate report, sha256 fa0374cb…).
Runtime artifacts (reports, receipts, checkpoints) follow the repository's
local outputs convention and are not Git assets.

| Modality | Ordering | Records | Updates | Tensors changed | Final checkpoint sha256 |
| --- | --- | ---: | ---: | ---: | --- |
| text-state | staged | 512 | 16 | 504/504 | sha256:fedb6e68b721c500… |
| text-state | shuffled | 512 | 16 | 504/504 | sha256:a67044d530d83fb4… |
| text-state | mixed_order | 512 | 16 | 504/504 | sha256:c61da29e32cb816b… |
| visual-state | staged | 512 | 16 | 504/504 | sha256:41018c4155cfb0d9… |
| visual-state | shuffled | 512 | 16 | 504/504 | sha256:36d92f4d2d1328e1… |
| visual-state | mixed_order | 512 | 16 | 504/504 | sha256:3dbddae8a303a085… |
| multimodal-state | staged | 512 | 16 | 504/504 | sha256:b21e0acda6d83593… |
| multimodal-state | shuffled | 512 | 16 | 504/504 | sha256:3ef3f57047b5df4c… |
| multimodal-state | mixed_order | 512 | 16 | 504/504 | sha256:f0a5c67860753673… |

Exposure verification (aggregate report, independently re-audited by the CPU
finalizer): all nine cells trained on the same 512-record set
(`same_record_set_all_cells: true`); each cell's trained order exactly matches
the protocol's frozen ordering list (`exact_protocol_orders_all_cells: true`;
staged sha256:dd7e62f0…, shuffled sha256:9b5c7ee5…, mixed_order
sha256:fa6485c6…); all nine cells began from the identical seed-17 fresh LoRA
initialization (`fresh_lora_init_identical_all_cells: true`,
sha256:9530a9ed…, 504 tensors). The three orderings are permutations of one
membership — staged = deterministic source-difficulty order (pair→difficulty
join frozen in the protocol), shuffled = seed-64 permutation, mixed_order =
difficulty round-robin. Source membership, corpus shards, views and scene
assets remain byte-identical (recursive per-file manifests in each receipt).
No intermediate checkpoints exist; no cell required recovery or retraining
(`recovered_without_retrain: false` everywhere); training losses are finite.
No development or final-panel diagnostics were declared or run.

Scheduler provenance: `curriculum-train-0` (GPU 0, port 18800, six cells,
1.426981 GPUh) and `curriculum-train-1` (GPU 1, port 18801, three cells,
0.797143 GPUh), one attempt each, both audit hooks returncode 0;
`curriculum-train-final` (CPU) independently re-verified all nine cells,
receipts, exposure and initialization equality, hook returncode 0. Training
consumed 2.224124 GPU-hours; curriculum branch cumulative 2.224124 / 48.
Runtime commit `cad75e6`. Missing coverage: none.

Verification (read-only; re-verifies all nine checkpoints, receipts, exposure
and initialization equality against the published report):

```bash
source ~/cd_vlaplan
EXPANDED_TERMINAL_PATH=outputs/expanded-study/v1/jobs/curriculum-train-final/1/terminal.json \
  python scripts/run_expanded_curriculum_training.py audit-training-final
```

`audit-training-worker` and `finalize-training` are mutating
repair/republication operations (they rewrite per-attempt checkpoint audits
and the aggregate report); run them only for a deliberate republication.

#119's training deliverable is satisfied; the fixed evaluation and the
predeclared interaction/saturation analysis follow in Goal 10 Phase 3/4.
Historical #67 remains a separate saturated study and is not pooled here.
