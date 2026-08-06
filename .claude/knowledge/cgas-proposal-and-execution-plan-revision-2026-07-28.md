# CGAS Proposal and Execution Plan Revision

Date: 2026-07-28

## 2026-07-31 release-scope quarantine

This note records a research-plan revision, not current release delivery. The only authorized current CGAS handoff is `data/planning_cgas_v1/release_manifest.json`. Any later live memory, calibration, route-label work, CGAS training or implementation, matched baselines, or attention analysis must start from that manifest and pass a new release or experiment gate.

## Documents revised

- `doc/research_proposal.md`
- `doc/high_level_plans/research_execution_plan.md`

## Decision

The ICLR 2027 story is now method-centered: Certificate-Guided Adaptive Scaffolding (CGAS) is the deferred hypothesis for learning the minimum-cost support needed to preserve a verifier-checked search certificate. The current release does not implement or train CGAS. The proposal no longer makes a broad claim about modality-specific cognitive affordances, hard boundaries, transfer of algorithmic bias, or attention as a central mechanism.

## Research gap

The proposal now positions CGAS against neural algorithmic reasoning, process supervision, adaptive computation, multimodal routing/tool use, and LLM planning. The bounded novelty claim is counterfactual minimum-cost scaffold selection from planner-certificate validity. It must remain "to our knowledge" and be re-audited before submission.

## Execution changes

The execution plan begins with trace provenance/alignment repair and BFS/IW certificate verification. As of 2026-07-31, the released handoff for future work is `data/planning_cgas_v1/release_manifest.json`. Later plans may add counterfactual generation, audited live memory, a small calibration gate, CGAS and matched baselines, and structural fidelity-cost evaluation, but those items are deferred and not delivered by the current release. FF/Graphplan and broad modality/transfer analyses remain secondary until their semantics and the core result are established.
