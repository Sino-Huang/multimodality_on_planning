# Observation Manifest

| observation_id | source | evidence layer | observer group | artifact/anchor | observation |
|---|---|---|---|---|---|
| O1 | `doc/research_proposal.md` | intent/spec | direct-read | lines 194-201 | Calibration precedes method run and requires a recurrent localized failure. |
| O2 | `doc/high_level_plans/research_execution_plan.md` | intent/spec | direct-read | lines 121-141 | Phase 3 is a gate before Phase 4; no recurrent failure means reconsider the direction. |
| O3 | `.omo/knowledges/cgas-dataloader-resume-blocker-2026-07-30.md` | historical receipt | direct-read | lines 3-13 | Earlier partition was empty/unapproved and Todo 5-6 were blocked. |
| O4 | `.omo/knowledges/cgas-release-boundary-manifest-handoff-2026-07-31.md` | release receipt | direct-read | lines 7-17 | Later release has 12 emitted rows and strict loader evidence; downstream method work remains deferred. |
| O5 | `.omo/knowledges/cgas-partition-approval-gate-2026-07-30.md` | feasibility receipt | direct-read | lines 18-21 | Successor bundle still failed structural-OOD coverage under active policy. |
| O6 | `.omo/knowledges/cgas-planner-alternative-profile-probe-2026-07-30.md` | executed probe receipt | direct-read | lines 3-11 | Tested alternative BFS/IW profiles did not justify an authoritative successor characterization. |
| O7 | `data/planning_cgas_v1/release_manifest.json` | release artifact | direct-read | line 1 | Release manifest binds source/alignment/steps/Qwen/preflight artifacts. |
| O8 | `doc/detailed_implementation_summary/phase3_cgas_todo6_native_qwen_loader_release_gate_2026-07-30.md` | implementation/QA receipt | direct-read | lines 22-35 | Strict preflight accepted all 12 rows and native loader produced image tensors/grid metadata. |
| O9 | `data/planning_cgas_v1/manifest.json` and source split JSONL | release artifact | direct-read | line 1 | Released train/dev/test sources are named fixture instances; structural-OOD member is three-object/horizon-two. |
| O10 | `scripts/phase3/cgas_release_gate.py` | implementation | direct-read | lines 29-48,100-107 | Release gate verifies corpus provenance/alignment/certificates/Qwen/preflight and binds `approved.json`, but has no real partition-approval input. |
| O11 | `.omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft*.json` | evidence integrity | executed hash check | SHA-256 output | Current draft hash `a7dda6e5...` differs from frozen rerun/receipt hash `409f7127...`. |
| O12 | four independent explore workers | independent codebase audit | worker-wave-1 | background outputs | Workers agree the 12-row handoff is real and deferred method work is absent; they disagree whether memory or corpus readiness should come first. |
