# Research note: training-framework selection for issues #52–#54 and downstream experiments

**Issues:** [#52 — BFS base and references](https://github.com/Sino-Huang/multimodality_on_planning/issues/52), [#53 — operational-only SFT](https://github.com/Sino-Huang/multimodality_on_planning/issues/53), and [#54 — process SFT and BFS sanity gate](https://github.com/Sino-Huang/multimodality_on_planning/issues/54), under [parent spec #38](https://github.com/Sino-Huang/multimodality_on_planning/issues/38)

**Scope:** Select an existing training framework for the governed BFS experiments and the later algorithm-by-modality, DAgger, end-to-end, and second-backbone experiments. This is a framework decision, not a training result.

**Status:** Research note only. No framework has been installed and no GPU training result is claimed here. Sources were checked on 2026-08-20.

---

## Recommendation

Use **[ms-swift](https://github.com/modelscope/ms-swift)** as the training substrate, pinned to an exact version or commit only after a dependency-preserving one-step GPU smoke test.

Keep the repository's Search Episode Harness, authorization receipts, invariant adjudication, frozen split/curriculum logic, and DAgger collector outside ms-swift. The framework should receive already-authorized model-facing records and produce checkpoints/adapters; it must not become the scientific evaluator or trusted runtime.

Why ms-swift:

1. The BFS freeze already selects `Qwen/Qwen3-VL-8B-Instruct`, LoRA, five seeds, and an exact core stack: Python 3.10 in the current environment, PyTorch 2.7.1, Transformers 4.57.0, Accelerate 1.5.2, and PEFT 0.17.1 ([frozen configuration](../configs/experiments/bfs_phase_freeze_v1.json)). ms-swift declares Python >=3.10, PyTorch >=2.0, Transformers >=4.33, and PEFT >=0.11,<0.20, so those frozen versions lie inside its published ranges ([installation matrix](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/GetStarted/SWIFT-installation.md), [requirements](https://github.com/modelscope/ms-swift/blob/main/requirements/framework.txt)).
2. It supports Qwen3-VL and other multimodal families including InternVL, which preserves the later targeted second-backbone option ([supported-model overview](https://github.com/modelscope/ms-swift/blob/main/README.md), [supported-model registry documentation](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/Instruction/Supported-models-and-datasets.md)).
3. One standard record format covers text-only, image, and multi-image SFT, and permits response-level loss control. That maps cleanly to the planned text-state, visual-state, and multimodal-state cells and to serialized typed-operation targets ([custom dataset format](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/Customization/Custom-dataset.md)).
4. It supports LoRA/full SFT, gradient checkpointing, DeepSpeed, local datasets, checkpoint resumption, and loading adapter weights without restoring stale optimizer/data-skip state. Those are the training primitives needed for frozen SFT cells and repeated SFT over aggregated DAgger corrections ([training capabilities](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/Instruction/Pre-training-and-Fine-tuning.md), [command-line parameters](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/Instruction/Command-line-parameters.md)).
5. The official Qwen3-VL repository points its fine-tuning best-practice users to ms-swift, providing upstream evidence specifically for this backbone rather than only a generic framework claim ([Qwen3-VL fine-tuning guidance](https://github.com/QwenLM/Qwen3-VL/issues/1656)).

This recommendation is contingent on the smoke gates in §7. A declared dependency range is not proof that the exact frozen model/stack trains on the available GPU.

## 1. Requirements derived from the experiment program

| Requirement | Authoritative project evidence | Framework consequence |
|---|---|---|
| Run base, random-valid, and exact-classical references before SFT | [#52](https://github.com/Sino-Huang/multimodality_on_planning/issues/52) | These are harness/evaluation jobs, not framework training jobs. |
| Train an operational-only LoRA SFT arm without process leakage | [#53](https://github.com/Sino-Huang/multimodality_on_planning/issues/53), [BFS corpus builder](../examples/planning_benchmark_slice/bfs_corpus.py) | Convert only `corpus/operational.jsonl`; preserve the corpus audit and immutable whole-instance split IDs. |
| Train process SFT and adjudicate full-episode BFS invariants | [#54](https://github.com/Sino-Huang/multimodality_on_planning/issues/54), [parent spec](https://github.com/Sino-Huang/multimodality_on_planning/issues/38) | Train a typed text output, but perform FIFO/invariant adjudication in the project harness, not with trainer loss/accuracy. |
| Use the frozen Qwen3-VL-8B backbone, five seeds, LoRA rank 64, deterministic optimization, fixed budgets, and no retuning | [BFS freeze](../configs/experiments/bfs_phase_freeze_v1.json) | The framework must accept the exact frozen core library and optimizer settings; convenience defaults cannot override them. |
| Extend the same design to matched text, visual, and text-image corpora | [#70](https://github.com/Sino-Huang/multimodality_on_planning/issues/70), [#73](https://github.com/Sino-Huang/multimodality_on_planning/issues/73), [#74](https://github.com/Sino-Huang/multimodality_on_planning/issues/74), [#76](https://github.com/Sino-Huang/multimodality_on_planning/issues/76) | Need text-only and image/multi-image records under one supervised objective. |
| Add DAgger corrections from student-visited states, then train 12 cells | [#78](https://github.com/Sino-Huang/multimodality_on_planning/issues/78), [#79](https://github.com/Sino-Huang/multimodality_on_planning/issues/79), [#84](https://github.com/Sino-Huang/multimodality_on_planning/issues/84) | Need repeatable adapter continuation from a newly aggregated corpus; no candidate supplies the project's trusted-runtime DAgger semantics. |
| Train a separately reported model-generated-successor arm | [#89](https://github.com/Sino-Huang/multimodality_on_planning/issues/89) | Need ordinary generative SFT with potentially longer structured targets; scientific separation remains a project concern. |
| Run targeted second-backbone replication | [#102](https://github.com/Sino-Huang/multimodality_on_planning/issues/102) | A Qwen-only framework would force a framework migration at the replication stage. |

The released BFS corpus is framework-neutral JSONL. Operational rows contain `input.{goal_atoms,source_state}` and `target.{action,target_state,validity}`; process rows contain `input.{goal_atoms,observation,search_memory}` and `target.{canonical_rationale,runtime_result,typed_operation}` ([builder](../examples/planning_benchmark_slice/bfs_corpus.py)). A small deterministic converter is required for every candidate; no candidate should read the governed corpus and silently decide how these objects are serialized.

## 2. Candidate comparison

| Candidate | Immediate #53/#54 fit | Later-program fit | Frozen-environment fit | Decision |
|---|---|---|---|---|
| **ms-swift** | Local/custom SFT datasets, LoRA, DeepSpeed, gradient checkpointing, explicit validation data, Python and CLI entry points ([training docs](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/Instruction/Pre-training-and-Fine-tuning.md)). | Text and multi-image records, Qwen3-VL plus non-Qwen VLMs, adapter continuation, and multimodal inference APIs ([custom data](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/Customization/Custom-dataset.md), [inference](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/Instruction/Inference-and-deployment.md)). DAgger collection remains external. | Its published ranges include the frozen PyTorch, Transformers, and PEFT versions ([installation matrix](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/GetStarted/SWIFT-installation.md)). Missing packages still have to be installed and tested. | **Select.** Best program-wide coverage without requiring known core-version drift. |
| **Qwen-VL-Series-Finetune (2U1)** | Strong Qwen-specific path: Qwen3-VL SFT, LoRA/QLoRA/full tuning, DeepSpeed, multi-image input, and mixed-modality data ([README](https://github.com/2U1/Qwen-VL-Series-Finetune)). | DPO/GRPO are present, but there is no project-specific DAgger loop, and the repository is explicitly Qwen-VL-series-only ([README](https://github.com/2U1/Qwen-VL-Series-Finetune)). A second non-Qwen backbone would require another framework. | Its current requirements pin PyTorch 2.8.0, Transformers 5.3.0, Accelerate 1.10.1, PEFT 0.15.2, and DeepSpeed 0.17.5, conflicting with the governed BFS freeze ([requirements](https://github.com/2U1/Qwen-VL-Series-Finetune/blob/master/requirements.txt)). | Reject as the project-wide framework. Useful only as a Qwen implementation reference. |
| **LlamaFactory** | Strong declarative SFT path with Qwen3-VL LoRA/full examples and custom text/image datasets ([examples](https://github.com/hiyouga/LlamaFactory/blob/main/examples/README.md), [data preparation](https://llamafactory.readthedocs.io/en/latest/getting_started/data_preparation.html)). | Supports Qwen3-VL and InternVL families, multiple tuning modes, and multimodal SFT ([model table and training modes](https://github.com/hiyouga/LlamaFactory#supported-models)). DAgger collection still remains external. | Current `main` requires Python >=3.11, explicitly excludes Transformers 4.57.0, and requires PEFT >=0.18.0; all conflict with the current governed environment/freeze ([pyproject](https://github.com/hiyouga/LlamaFactory/blob/main/pyproject.toml)). An older pin might work but would require a separate compatibility proof and could lose current Qwen3-VL support. | Reject for these frozen BFS runs. Reconsider only under a new governed freeze. |
| **Official Qwen3-VL `qwen-vl-finetune`** | It is the upstream Qwen training reference and supports custom single/multi-image conversation data and LoRA ([official training README](https://github.com/QwenLM/Qwen3-VL/blob/main/qwen-vl-finetune/README.md)). | Qwen-only, so it cannot carry the second-backbone replication without migration. DAgger remains external. | Its documented recipe uses PEFT 0.17.1 and Transformers 4.57.0.dev0 but different PyTorch, Accelerate, and DeepSpeed versions from the freeze ([official requirements](https://github.com/QwenLM/Qwen3-VL/blob/main/qwen-vl-finetune/README.md#requirements)). | Keep as the model-specific correctness reference and fallback, not the program-wide framework. |

### Why broad preference/RLHF support is not the deciding factor

The planned DAgger arm is not DPO, GRPO, or PPO. It has repository-specific semantics: reject an invalid student action, query the algorithmic expert at the last valid state, retain rollout/correction linkage, and replay the correction exactly ([#78](https://github.com/Sino-Huang/multimodality_on_planning/issues/78)). None of the candidates implements that contract. The correct boundary is:

1. the project harness collects and certifies interactions/corrections;
2. the project converter serializes the accumulated supervised records;
3. ms-swift performs the next SFT/LoRA update;
4. the project harness evaluates the resulting adapter without repair.

ms-swift's ability to load only model/adapter weights when the dataset changes is relevant to this cycle; restoring the old optimizer position and old data-skip state would be incorrect for a newly aggregated corpus ([resume parameters](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/Instruction/Command-line-parameters.md)).

## 3. Proposed ownership boundary

### Repository-owned (scientific contract)

- authorization and PASS / VALID_STOP / INVALID / ANCESTOR_STOP receipts;
- immutable whole-instance splits, curricula, leakage checks, and data hashes;
- canonical serialization of state, goal, search memory, rationale, typed operation, and runtime result;
- Search Episode Harness inference loop, invalid-operation charging, and no-repair evaluation;
- algorithm-invariant verification, random-valid/exact references, and full-episode metrics;
- DAgger collection, expert queries, aggregation budgets, correction linkage, and replay;
- seed-to-run/checkpoint manifests and selection only on the frozen development metric.

### ms-swift-owned (optimization machinery)

- model and processor construction for supported backbones;
- assistant-token loss masking and multimodal collation;
- LoRA attachment, gradient checkpointing, bf16, optimizer/scheduler execution, and distributed training;
- checkpoint/adapter persistence and model-facing training logs.

This seam prevents trainer convenience metrics from being mistaken for algorithm-valid episode evidence.

## 4. Data mapping

Use ms-swift's standard `messages` JSONL format ([schema](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/Customization/Custom-dataset.md)):

- **Text-state:** one user message containing the canonical serialized input object; one assistant message containing the canonical serialized target object.
- **Visual-state:** the same message shape with the required `<image>` placeholders and an `images` list. A state frame and partial-goal image can be represented as two ordered images.
- **Multimodal-state:** include both the canonical text input and the same ordered image list.
- **Targets:** serialize the complete target as canonical JSON. Do not rely on free-form rationale parsing for authoritative fields.
- **Metadata:** retain record ID, split assignment, source hashes, modality, algorithm, arm, seed, and receipt in a sidecar/run manifest. Do not put non-input provenance into the prompt.

The converter should emit one dataset per frozen arm/modality/algorithm/seed cell, plus a manifest binding every emitted example back to its governed source row. This preserves the existing contamination audit: the operational converter must never read process-only fields.

## 5. Configuration rules for #53 and #54

The [frozen BFS configuration](../configs/experiments/bfs_phase_freeze_v1.json) is authoritative. The ms-swift config must explicitly carry, rather than infer from defaults:

- `Qwen/Qwen3-VL-8B-Instruct` at the frozen model revision;
- LoRA rank 64, alpha 128, dropout 0.05, no bias, all-linear targets;
- bf16, three epochs, global batch size 32, gradient checkpointing;
- AdamW, learning rate `1e-4`, cosine schedule, warmup ratio 0.03, max gradient norm 1.0, zero weight decay;
- seeds 17, 29, 43, 71, and 101;
- maximum context 4096 and output budget 256;
- an explicit frozen train/dev dataset and no access to the test split;
- deterministic-algorithm settings and complete environment/config capture.

Framework-reported evaluation loss is diagnostic only. Checkpoint selection remains `dev_invariant_valid_episode_success`, computed through the Search Episode Harness.

## 6. Known gaps and risks

1. **No GPU proof yet.** ms-swift's declared compatibility does not prove Qwen3-VL-8B LoRA fits or runs correctly on the current GPU.
2. **Missing environment packages.** On 2026-08-20, the mandated environment had the frozen PyTorch/Transformers/Accelerate versions but did not have PEFT, ms-swift, TRL, ModelScope, or torchaudio installed. Installation must not silently upgrade frozen packages.
3. **Exact determinism needs proof.** CUDA kernels, attention backends, data-worker order, and distributed execution can violate a nominal deterministic flag. Byte-identical corpus regeneration does not imply byte-identical checkpoint weights.
4. **Curriculum order must be explicit.** ms-swift shuffles training data by default and exposes a `train_dataloader_shuffle` control ([data arguments](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/Instruction/Command-line-parameters.md)). The staged curriculum and mixed-order control therefore require separately frozen dataset/order settings.
5. **Model-facing conversion is new work.** The governed corpus is not currently an ms-swift dataset. Label masking, truncation, image ordering, and target round-trip must be tested before scientific training.
6. **Second backbone remains unselected.** Framework support keeps the option open; it does not authorize or choose the model. [#102](https://github.com/Sino-Huang/multimodality_on_planning/issues/102) remains governed by its own predecessor decision.

## 7. Required adoption gates before a scientific run

1. Pin an ms-swift release/commit in an isolated workspace and resolve dependencies while constraining every frozen core version. Abort on any forced core-version change.
2. Convert a tiny authorized operational/process fixture to `messages` JSONL and prove exact source-ID and target round-trip.
3. Use ms-swift's template encoder to prove that prompt/input tokens are masked and every canonical assistant target token is labeled; verify operational rows contain no process-only keys.
4. Run a one-step Qwen3-VL-8B LoRA smoke on the actual GPU with the frozen attention, precision, context, and LoRA settings. Record peak allocated/reserved VRAM and wall time.
5. Save and reload the adapter, then run one project-harness episode to prove parser and processor compatibility.
6. Repeat a tiny fixed-seed run twice and compare example order, logged loss sequence, adapter tensors, and decoded output. Any nondeterminism must be recorded and governed before the five-seed runs.
7. Only after these gates pass, add the exact ms-swift pin and complete resolved environment to the authorization manifest used by issues #53/#54.

## 8. Bottom line

**Choose ms-swift**, with a deliberately narrow role as optimizer/checkpoint machinery behind the repository's governed data and Search Episode Harness. It is the only compared program-wide framework whose published dependency ranges include the already-frozen BFS stack while also covering Qwen3-VL, later visual/multimodal SFT, iterative adapter training, and a non-Qwen second backbone. LlamaFactory is functionally attractive but currently incompatible with the frozen runtime; the community and official Qwen trainers are useful references but are too Qwen-specific for the full program.


## 9. Execution update (2026-08-20)

The mandated environment accepted ms-swift 4.2.2 while preserving the frozen core versions: PyTorch 2.7.1, Transformers 4.57.0, Accelerate 1.5.2, and PEFT 0.17.1. The exact frozen Qwen revision also completed a governed greedy inference smoke on an A100 80 GB, peaking at 17,822,138,880 allocated bytes in 45.95 seconds; its evidence replayed independently.

This is not the one-step LoRA adoption smoke required above. The issue-52 exact-classical reference missed the frozen 1.0 success threshold, so issues #53 and #54 are ancestor-stopped before training. Consequently, no scientific SFT was started and no ms-swift pin was added to the frozen authorization or project requirements. The framework recommendation remains conditional for a future newly authorized phase.
