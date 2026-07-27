# Wave 1: Local Proposal Audit

## Key findings

- The proposed resource matrix is not factorial: it has V, L, V+L, and V+L+T, but the CRSH claims require all subsets of {V, L, T}; this blocks necessity and hard-boundary inference.
- The current zero-shot path packages prompts and performs lexical fidelity scoring. It is not a model evaluation, nor a semantic execution verifier.
- The tool arm is a gold-formatted static payload rather than an agent-operated read/write interface, and the visual arm lacks aligned render artifacts in the relevant smoke evidence.
- The proposal instructs the named algorithm during training/prompting. Its current design therefore cannot distinguish learning to imitate a supplied trace from spontaneous algorithm selection.
- There is an unresolved BFS versus GBFS and exact-versus-approximate planner semantics mismatch across the documents and active pipeline.

## Evidence anchors

- `doc/research_proposal.md:32-56, 94-105, 162-181, 607-610`
- `examples/planning_benchmark_slice/zero_shot.py:359-365, 482-491`
- `examples/planning_benchmark_slice/modality_serializers.py:268-301`
- `.sisyphus/evidence/phase1-3-task-9-serialize.json:52-196`
- `.sisyphus/evidence/phase1-3-task-11-no-overclaim.json:8-26`
- `doc/detailed_implementation_summary/phase3_expert_trajectories_summary.md:13-20`

## EXPAND

- LEAD: Validate closest-work and any first-systematic-comparison claim. WHY: novelty cannot rest on local assertions. ANGLE: search-trace and multimodal-planning literature.
- LEAD: Specify a live external-memory interface and causal intervention protocol. WHY: static scratchpad serialization does not test tool use. ANGLE: tool-use and mechanistic interpretability literature.
