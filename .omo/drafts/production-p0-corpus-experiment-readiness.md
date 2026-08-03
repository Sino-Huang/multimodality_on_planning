---
slug: production-p0-corpus-experiment-readiness
status: ready-for-execution
intent: clear
review_required: true
plan_path: .omo/plans/production-p0-corpus-experiment-readiness.md
plan_sha256: e995f270f5c5ba40725100012c439c272cbec98f4e15fd5c5dcd21af7c67cbd7
review_round_id: df437370-d5d2-40ef-8005-bf64938a2675
round_status: approved
pending-action: hand off .omo/plans/production-p0-corpus-experiment-readiness.md for $start-work
review:
  momus:
    status: approved
    workspace_root: /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
    runtime_home: /home/sukaih/.config/opencode
    target: .omo/plans/production-p0-corpus-experiment-readiness.md
    round_id: df437370-d5d2-40ef-8005-bf64938a2675
    plan_sha256: e995f270f5c5ba40725100012c439c272cbec98f4e15fd5c5dcd21af7c67cbd7
    launch_id: bg_8c0683af
    session: ses_03db18e83ffeiJQ6uuIHoe2WlF
    result: "OKAY: executable; references support claims; tasks have concrete starts, dependency gates, commands, and expected QA with no blocking contradictions. Initial background attempt timed out before analysis; same session resumed to verdict."
  independent:
    status: approved
    workspace_root: /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
    runtime_home: /home/sukaih/.config/opencode
    target: .omo/plans/production-p0-corpus-experiment-readiness.md
    round_id: df437370-d5d2-40ef-8005-bf64938a2675
    plan_sha256: e995f270f5c5ba40725100012c439c272cbec98f4e15fd5c5dcd21af7c67cbd7
    launch_id: bg_6b247e06
    session: ses_03db18cdeffeKRsj2Gm3CaUcfR
    result: "OKAY"
approach: Generate a compositionally diverse non-fixture Blocksworld candidate pool, retain only paired-exact canonical FIFO BFS and width-1 IW instances, select and separately owner-approve the scientific P0 partition, regenerate the complete aligned/certified release, then add an independent four-backbone VLM adapter and smoke/evaluation readiness layer without continuous-action VLA dependencies.
---

# Draft: production-p0-corpus-experiment-readiness

## Review history
- Round `f75116fb-5e0b-47f2-8cc9-e9fcd2a86333`, plan SHA-256 `4366d7367dc2870726841d0608194ee2fc5fb2e069e889099c971e289cd1e427`: Momus and Oracle rejected the impossible exact-320 four-object claim; Oracle also required verification before old-tree retirement and atomic checksummed journal generations.
- The user then selected historical partial goals and separately approved a versioned trace-persistence migration after code inspection proved unsolved complete or partial goals cannot produce complete traces under the trace-v1 `max_trace_steps=1` override.
- Round `6fd631a0-91b5-493b-8c1e-1569b6175c8c`, plan SHA-256 `bd16f6e76cbbbb4c9302a9d271534ca3dc7b2de47fa5e8b59680094d3a8fc461`: Momus approved; Oracle required selector-failure feedback expansion, an exact candidate canonicalization/rank algorithm, and a checksum preimage excluding `record_sha256`.
- Round `97dca431-3c4f-4804-8779-86aa6092ab52`, plan SHA-256 `0a324c13bc4b6d36fedaccbc15b650e0e793ae8cfcf54a99fd5e21086978d131`: both reviewers required exact Lehmer/leaf bytes, raw accounting distinct from emitted-only planner work, topological Todo 11 placement, and runnable Todo 4/10 commands.
- Round `26d6a5c4-0477-4139-881c-6c4887087d55`, plan SHA-256 `b8c1fabe8aa6a752810d49943fcf4ac62e064ed8d80f7674c99f03d96fe12632`: Oracle approved; Momus required copy-pastable Todo 2/3/F3 commands and expected artifact/cursor signals.
- Round `241d06d0-6cbb-4cc0-a588-8fa770f50016`, plan SHA-256 `deb1a537ea05b819dc01770cabcbd8511c552ce0706f371392364b5b97a2178d`: Momus approved; Oracle required a later-round immutable candidate slice interface, explicit recovery for prepared-after-exchange and verified-after-backup filesystem-only windows, and fully resolved F3 commands.
- Round `d2ccc6ac-a7c0-42d3-80cf-c3226c55000f`, plan SHA-256 `3c6aa18830ccc51461f947a311acfb7dfa1382fb1d6442d3ab27b9746c318c92`: both reviewers rejected prefix-terminal fragments that overlapped later quota batches; Oracle also required historical checkpoint replay to verify ancestry without rolling `current.json` backward.
- Round `df437370-d5d2-40ef-8005-bf64938a2675`, plan SHA-256 `e995f270f5c5ba40725100012c439c272cbec98f4e15fd5c5dcd21af7c67cbd7`: Oracle returned `OKAY`; Momus timed out before analysis, then the same session resumed and returned `[OKAY]`. Final dual review approved.

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
1 | Production candidate generation | active | `src/data_collect/cli.py:121-124,233-275`; `.omo/ulw-research/20260801-002131/SYNTHESIS.md:19-33`
2 | Paired-exact characterization | active | `scripts/phase3/cgas_provenance.py:31-167`; `scripts/phase3/cgas_partition_selection.py:112-148`
3 | Scientific partition and owner approval | active | `scripts/phase3/cgas_partition_selection.py:14-18,39-169`; `scripts/phase3/cgas_partition_approval.py:16-49`
4 | Production release regeneration | active | `scripts/phase3/cgas_release_gate.py:29-113`; `scripts/phase3/cgas_qwenvl_preflight.py:25-117`
5 | Four-backbone VLM experiment preflight | active | `starVLA/model/modules/vlm/__init__.py:1-40`; `starVLA/training/train_starvlm.py:226-280`; `starVLA/dataloader/vlm_datasets.py:246-310`

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->
- Experiment readiness means adapters, deterministic configs, train/dev/test loading, one-batch loss smoke, one-record generation smoke, prediction parsing, metrics, and run manifests; it excludes full fine-tuning and research-result interpretation | Matches “readiness” and preserves the corpus-first gate | reversible.
- Extend the existing deterministic curriculum generation workflow with a dedicated CGAS production profile and output root; do not overwrite `data/curriculum_pddl` or the 12-row fixture release while candidates are being evaluated | Reuses accepted generation/provenance conventions and protects existing evidence | reversible.
- Preserve the active selector constants and paired-exact definitions exactly | The current blocker is input diversity, not a justified policy or planner change | reversible only through a separate owner decision.
- Keep the current 12-row corpus as an explicitly named infrastructure fixture after publishing a superseding production release | Maintains regression coverage without treating fixture rows as research data | reversible.
- Build a standalone `planning_vlm` experiment package that may reuse narrow optimizer/checkpoint helpers but does not call `build_framework`, action heads, FAST action tokenizers, LeRobot, or robot evaluators | Current trainer/loader are Qwen- and VLA-coupled | reversible.
- Use TDD for all production behavior, with focused RED/GREEN tests plus real CLI model/data smoke; no model download is hidden inside unit tests | Required project workflow and reproducibility | reversible only by explicit test-strategy decision.
- Generated large corpus/model outputs remain local artifacts bound by manifests; code, configs, tests, schemas, and summaries are Git-tracked | Existing plan guardrail avoids accidental large-data commits | reversible owner distribution decision.
- Preserve the active 481-row authoritative population contract exactly: split counts `train=402`, `dev=39`, `test=40` and object counts `4=190`, `8=198`, `12=93` | `scripts/phase3/cgas_partition_contracts.py:9-12` and run-contract validation reject any other population | requires a separate versioned owner-approved migration to change.
- Use historical partial goals containing only positive `on(...)` atoms, complete stable initial states, and shared-renaming canonical candidate identities distinct from selector signatures | The user selected this encoding after the complete-state alternative proved incompatible with the old one-event trace persistence | reversible only through a separate scientific-contract decision.
- Preserve trace-v1 fixture bytes and search behavior exactly, while adding separately owner-approved `cgas_trace_contract_v2` bounded-memory event-stream persistence for production | The user approved a versioned persistence migration after both complete and partial unsolved goals proved unable to produce complete traces under `max_trace_steps=1` | reversible only through a separate owner decision.

## Findings (cited - path:lines)
- The verified 12-row release is infrastructure-only; it has four rows per split and one three-object structural-OOD fixture: `.omo/knowledges/cgas-next-step-assessment-2026-08-01.md:3-9`.
- Active selection requires exactly 39 calibration rows, at least 20 dev and test rows, whole-composition isolation, and at least 10 structural-OOD signatures: `scripts/phase3/cgas_partition_selection.py:14-18,39-169`.
- Current 481-row production evidence is blocked first by incomplete paired-exact 12-object rows; a successor repaired exactness but still has only three signatures: `tests/phase3/test_cgas_partition_selection_real_bundle.py:45-95`.
- Owner approval is a separate exact-byte contract, while the current release manifest does not consume that artifact: `scripts/phase3/cgas_partition_approval.py:16-49`; `scripts/phase3/cgas_release_gate.py:100-107`.
- Existing release publication already gates provenance, alignment, certificates, Qwen conversion, and strict loader preflight: `scripts/phase3/cgas_release_gate.py:29-68`.
- The model target is canonical assistant JSON containing only `action` and `certificate`; model inputs deny planner traces, replay transitions, and route labels: `scripts/phase3/cgas_qwenvl_contracts.py:52-82,146-224`.
- Qwen3-VL and Molmo2 wrappers exist, but InternVL3.5 and Zamba2-VL are not dispatched: `starVLA/model/modules/vlm/__init__.py:1-40`.
- The native loader supports only Qwen model types and uses model-specific token logic: `starVLA/dataloader/vlm_datasets.py:204-269`.
- The VLM trainer still constructs a VLA framework and has no model-generation evaluation: `starVLA/training/train_starvlm.py:226-280,318-371`; `starVLA/model/framework/base_framework.py:183-203`.
- The authoritative characterization contract is hard-bound to 481 rows and fixed split/object quotas: `scripts/phase3/cgas_partition_contracts.py:9-12,59-69`; `scripts/phase3/cgas_characterization_contract.py:154-165`.
- Production characterization currently overrides the default `max_trace_steps=10000` to `1`, so multi-event successful BFS/IW searches are marked truncated even though search limits permit them: `scripts/phase3/cgas_characterization_rows.py:20-24`; `scripts/phase3/cgas_bfs.py:38-73`; `scripts/phase3/local_iw.py:47-89`.
- Alignment consumes a previously generated render manifest, so production rendering is an explicit prerequisite rather than part of alignment: `scripts/phase3/cgas_alignment.py:45-63,117-161`.
- The repository pins Transformers 4.57.0 globally while model-specific comments already acknowledge a 5.3.0-incompatible alternative: `requirements.txt:1,35-41`; one shared runtime cannot be assumed for all four approved backbones.

## Decisions (with rationale)
- The critical path is production candidate diversity -> paired-exact characterization -> selector feasibility -> exact owner approval -> full release regeneration -> four-model experiment preflight.
- Candidate generation will deliberately vary Blocksworld initial/goal composition families and deterministic seeds, then filter by the existing exact planner contracts; it will not increase planner limits to manufacture eligibility.
- Candidate generation uses an exact shared-renaming graph identity and historical partial goals: four objects have 600 raw positions, 228 pair orbits, 18 task-solved orbits, and 210 nontrivial candidates; eight- and twelve-object spaces remain finite lazy cursor streams with no per-family quota.
- Trace-v2 changes persistence only: search limits, action ordering, plans, statuses, IW width, recovery policy, paired-exact semantics, and selector constants remain unchanged. Its exact migration packet requires independent owner approval before characterization, separate from scientific partition approval.
- Candidate discovery may be larger than 481 rows, but authoritative publication remains: arbitrary-size candidate characterization -> paired-exact/signature filtering -> deterministic assembly of the exact 481-row split/object topology -> full authoritative re-characterization -> selector draft.
- The selector and approval artifacts remain separate. Execution must pause at the generated non-empty draft until the owner signs the exact draft bytes; no worker may generate `owner_approved=true` autonomously.
- A fail-closed materializer must join approved role records back to exact source-manifest/PDDL bytes before provenance generation; approval JSON alone is not a corpus.
- Production transition rendering must produce exactly one semantically verified pre-action image per accepted source transition before alignment runs.
- The production release gate must bind the approved scientific partition in addition to existing corpus-byte/provenance checks, while preserving the prior release on failure.
- All release stages must execute under one sibling candidate root and atomically replace the canonical production root only after complete acceptance; no intermediate provenance publication may displace the fixture release.
- A canonical model-independent sample stays authoritative. Each model adapter owns chat-template, image preprocessing, label masking, loading, and decoding details.
- Readiness metrics include JSON parse rate, schema validity, exact action match, certificate exact/field accuracy, verifier acceptance, replay-valid action rate, first certificate failure, latency, and token counts.
- Full training, calibration conclusions, route labels, CGAS routing, bounded memory, and main sweeps begin only in later plans after this readiness gate.

## Scope IN
- Dedicated non-fixture Blocksworld P0 generation/sampling profile and immutable candidate manifest.
- Exact BFS/IW characterization, feasibility reporting, deterministic role-bearing draft, and exact-byte owner-approval checkpoint.
- Production alignment, certificate/counterfactual, canonical VLM dataset, strict processor checks, and superseding release manifest.
- Independent VLM-only adapter/config/train-smoke/generation/evaluation surfaces for Qwen3-VL, Molmo2, InternVL3.5, and Zamba2-VL.
- Run manifests, model/checkpoint revision pins, dataset release digest, seeds, generation parameters, environment/runtime versions, metrics, and implementation summary commands.

## Scope OUT (Must NOT have)
- No selector-policy weakening, planner-limit escalation, GBFS-to-BFS relabeling, incomplete IW traces, or fixture promotion as scientific data.
- No autonomous owner approval and no replacement of frozen evidence without a fresh receipt.
- No StarVLA continuous-action heads, FAST action tokenizer, LeRobot tensors, robot state/action normalization, or robot-environment evaluation.
- No full fine-tuning sweep, paper-result interpretation, route-label generation, live memory, CGAS controller, confidence router, or attention analysis.
- No committing model checkpoints, generated image corpora, experiment outputs, secrets, or machine-local absolute paths.

## Open questions
- None. The owner approved: immutable fixture archive `data/planning_cgas_fixture_v1`; canonical production root `data/planning_cgas_v1`; historical partial goals; a separately owner-approved persistence-only trace-v2 migration with trace-v1 preserved; isolated pinned Conda environments for incompatible model families; required official remote code only; sequential smoke on a >=40 GB GPU; and model IDs `Qwen/Qwen3-VL-8B-Instruct`, `allenai/Molmo2-8B`, `OpenGVLab/InternVL3_5-8B-HF`, and `Zyphra/Zamba2-VL-7B`.

## Approval gate
status: approved-for-execution-handoff
<!-- When exploration is exhausted and unknowns are answered, set status: awaiting-approval. -->
<!-- That durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->

The user approved the core approach, 7-8B matrix, artifact paths, and isolated runtime policy. The decision-complete plan has passed digest-bound Momus and Oracle review. No implementation has begun; execution starts only when the user invokes `$start-work` for `.omo/plans/production-p0-corpus-experiment-readiness.md`.
