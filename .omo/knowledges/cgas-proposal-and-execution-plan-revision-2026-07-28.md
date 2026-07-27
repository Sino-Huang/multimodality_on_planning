# CGAS Proposal and Execution Plan Revision

Date: 2026-07-28

## Documents revised

- `doc/research_proposal.md`
- `doc/high_level_plans/research_execution_plan.md`

## Decision

The ICLR 2027 story is now method-centered: Certificate-Guided Adaptive Scaffolding (CGAS) learns the minimum-cost support needed to preserve a verifier-checked search certificate. The proposal no longer makes a broad claim about modality-specific cognitive affordances, hard boundaries, transfer of algorithmic bias, or attention as a central mechanism.

## Research gap

The proposal now positions CGAS against neural algorithmic reasoning, process supervision, adaptive computation, multimodal routing/tool use, and LLM planning. The bounded novelty claim is counterfactual minimum-cost scaffold selection from planner-certificate validity. It must remain "to our knowledge" and be re-audited before submission.

## Execution changes

The execution plan begins with trace provenance/alignment repair and BFS/IW certificate verification. It then adds counterfactual generation, audited live memory, a small calibration gate, CGAS and matched baselines, and structural fidelity-cost evaluation. FF/Graphplan and broad modality/transfer analyses are secondary until their semantics and the core result are established.
