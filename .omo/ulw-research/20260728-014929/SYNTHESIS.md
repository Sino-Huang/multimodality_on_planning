# ULW-Research Synthesis: Method-Centered ICLR 2027 Revision

Sources: 20 primary/local sources across the two revisions · Online-method wave: 2026-07-28 · Empirical verifications: none; the method remains a proposal

## Executive verdict

**Yes, there is a credible method paper, but the method must replace the “learnability manifold” as the headline.** Generic trace supervision, adaptive computation, multimodal routing/dropout, tool invocation, and process-reward trajectory ranking are already established [R1-R8]. The paper should instead introduce a planning-specific intervention: **Certificate-Guided Adaptive Scaffolding (CGAS)**. CGAS adaptively invokes the minimum-cost support required to preserve a planner-executable search invariant, rather than routing from generic uncertainty, modality quality, or heuristic tool reward.

The resource analysis remains necessary but small: run a short calibration phase to identify the dominant certificate failures and fix the scaffold palette before the main experiment. The paper's evidence should then be method-first: CGAS versus static VLA, always-on scaffold, generic confidence routing, process-supervision/ranking, and modality dropout. Attention is appendix-level diagnostic evidence, not a contribution.

## The revised story

### Title

**Certificate-Guided Adaptive Scaffolding for Multimodal Search Planning**

### One-sentence pitch

*Multimodal planners fail when their next search-state update violates a verifiable invariant; CGAS predicts that risk and activates the cheapest planning scaffold that restores the invariant, improving structural generalization without always paying for tools or long traces.*

### Central claim

CGAS is not “a router that chooses a modality.” It is a **cost-aware policy over certified search state**. For a candidate next certificate `c_hat`, a lightweight controller decides among `direct`, `compact-certificate`, and `external-memory` scaffolds. Its decision is trained with counterfactual labels obtained from the planner verifier: the minimum-cost scaffold that makes the next transition satisfy the specified invariant. The main metric is verified process fidelity at a given resource cost.

This puts the novelty in a concrete algorithm and a new supervision signal, not in a descriptive account of attention or modality bias.

## Proposed method: CGAS

### Search certificate

Each planner state has a compact, typed certificate rather than a free-form rationale:

- BFS: frontier head/ordering summary, visited-set delta, candidate expansion identity.
- IW: novelty tuple, seen-feature delta, width decision.
- FF: named relaxed-goal support and the declared heuristic approximation.
- Graphplan: proposition/action-layer delta and mutex witness.

The executable planner checks these fields against the known transition. This is a natural fit for the repository's planner traces, but the current data needs semantic fidelity validation and reconciled BFS/GBFS semantics before it can train CGAS [R15-R18].

### Adaptive scaffolding policy

At each step, the backbone proposes an action and certificate. A small controller consumes the compact certificate, prior scaffold use, and a fixed-size representation of the current observation. It chooses the cheapest action in this fixed palette:

1. **Direct:** no scaffold; predict the next certificate and action.
2. **Compact certificate:** expose the previous verified certificate plus a bounded delta slot.
3. **External memory:** retrieve/update only the certificate entries keyed by the current search state; do not paste a gold queue or full planner trace into context.

The palette deliberately excludes a generic “send more modalities” choice. Raw vision/language stay fixed in the principal VLA experiment, so the result is not confounded with changing task information. Vision-only/language-only variants are secondary stress tests for the learned policy.

### Counterfactual minimum-cost supervision

For each oracle state, construct valid and minimally invalid certificate updates. The verifier identifies the earliest violated invariant. Replay the step under each allowed scaffold and label the least costly scaffold that gives a valid update. Train:

`L = L_action + lambda * L_certificate + alpha * L_route + beta * scaffold_cost`

where `L_route` supervises the minimum-cost valid scaffold, not a human rationale or generic confidence threshold. During inference, the controller uses only the predicted certificate and permitted live memory result; it never receives the oracle label.

This is the key distinction from process-reward DPO [R1], generic adaptive computation [R2-R3], and self-regulated visual tool invocation [R4]. The claim is still prospective: it needs direct baselines and a carefully documented counterfactual generator.

## Why this is better than the first story

| Earlier framing | Problem | CGAS revision |
|---|---|---|
| Resource learnability manifold | Broad descriptive result; can read as a large ablation paper. | One method that uses resources selectively. |
| Attention mechanism | Expensive and correlational unless extensive causal work is added. | One compact certificate-risk diagnostic; attention is optional appendix evidence. |
| Always-on external scratchpad | Confounds tool help with injected oracle state and cost. | Live, bounded, state-keyed certificate memory selected only when needed. |
| Invariant-Gated Process Repair | Could be dismissed as loss reweighting/hard-example mining. | Counterfactual minimum-cost routing is an observable algorithmic policy. |

## Compact analysis plan

Run only enough analysis to freeze the method before the main experiment:

1. Train a small static VLA baseline on short traces.
2. On held-out calibration instances, tally first certificate violation by planner family, horizon, and available representation.
3. Choose the fixed certificate schema and scaffold palette from this tally; preregister both before CGAS training.
4. In the paper, show one failure matrix and one route-calibration plot. Do not promise a full attention-map study.

Use a targeted causal check only if needed: mask the controller's certificate input or replay a verified certificate at a matched failing step. If route quality and fidelity change as predicted, that is enough method validation. Attention heads are not needed for the main claim.

## Main experiment

### Core scope

Make BFS and IW the primary setting, because their certificate and memory requirements are crisp. Use FF and Graphplan as out-of-family generalization only after their semantics are made exact or explicitly labelled as approximations. This improves statistical power and avoids the current BFS/GBFS inconsistency [R15-R18].

### Required baselines

- Static VLA, no scaffold.
- VLA with always-on compact certificate.
- VLA with always-on external memory, budget-matched to CGAS.
- Generic confidence/entropy router with the same palette and controller parameters.
- Uniform trace/process supervision; process-reward or trajectory-ranking comparator where feasible [R1].
- Generic modality dropout/robust-fusion comparator [R5-R7].

### Primary outcomes

- Verified certificate transition fidelity.
- Valid-plan success on larger object count, deeper plans, and higher branching factor.
- Average scaffold cost: tool calls, retrieved certificate bytes, and additional tokens.
- Route optimality: fraction of decisions matching the oracle minimum-cost valid scaffold.

The result must demonstrate the three-way trade-off: CGAS achieves higher structural OOD fidelity than direct VLA and lower resource cost than always-on memory. Final task success alone is insufficient.

## Reviewer-facing contribution statement

1. We introduce CGAS, a certificate-guided controller that adaptively allocates bounded planning scaffolds using verifier-derived minimum-cost supervision.
2. We develop counterfactual certificate supervision for learning when a multimodal planner needs structured state support, rather than merely supervising longer rationales or generic tool choice.
3. We show that CGAS improves verifier-checked search fidelity and structural generalization while reducing scaffold cost, with a calibration study that exposes when multimodal context is insufficient.

Avoid “first multimodal planner,” “attention explains planning,” “hard cognitive boundary,” and “tools are necessary for BFS.” The valid novelty claim is method-specific and bounded: *to our knowledge, prior adaptive systems do not train scaffold selection from counterfactual planner-certificate validity and minimum resource cost.* Keep this as “to our knowledge” until a final pre-submission search.

## Red-team risks and responses

| Reviewer objection | Required response |
|---|---|
| “This is confidence routing.” | Match its controller, palette, and cost; show certificate-validity labels improve route optimality and OOD fidelity. |
| “This is process supervision.” | Compare to uniform process targets and process-reward ranking; isolate the counterfactual minimum-cost route objective. |
| “The tool stores oracle state.” | Use an environment-owned live store; all entries must be predictions or prior verifier-approved outputs. Audit every read/write. |
| “The method just adds compute.” | Report matched budget curves and show lower cost than always-on scaffold at matched fidelity. |
| “The visual result is representation leakage.” | Keep raw observation fixed in the core VLA comparison, publish leakage tests, and make unimodal settings secondary. |
| “Why only BFS/IW?” | State that CGAS targets stateful search. Validate transfer to additional families only when their certificates are semantically exact. |

## Sources

- **[R1]** Jiao et al., *Learning Planning-based Reasoning by Trajectories Collection and Process Reward Synthesizing*, EMNLP 2024. https://arxiv.org/abs/2402.00658
- **[R2]** Neumann et al., *Learning to Reason With Adaptive Computation*, 2016. https://arxiv.org/abs/1610.07647
- **[R3]** Figurnov et al., *Differentiable Adaptive Computation Time for Visual Reasoning*, CVPR 2020. https://doi.org/10.1109/CVPR42600.2020.01283
- **[R4]** Chen et al., *Beyond the Eye: Efficient Multimodal Reasoning via Self-Regulated Implicit Visual Tools*, 2026. https://arxiv.org/abs/2607.11106
- **[R5]** Maheshwari and Sarcar, *Learnable Irrelevant Modality Dropout for Multimodal Action Recognition*, CVPR 2022. https://doi.org/10.1109/CVPR52688.2022.01957
- **[R6]** Zhao et al., *SMIL: Multimodal Learning with Severely Missing Modality*, AAAI 2021. https://doi.org/10.1609/aaai.v35i3.16330
- **[R7]** Zhu et al., *Unbiased Missing-Modality Multimodal Learning*, ICCV 2025. https://doi.org/10.1109/ICCV51701.2025.02272
- **[R8]** Lightman et al., *Let's Verify Step by Step*, 2023. https://arxiv.org/abs/2305.20050
- **[R9]** Veličković et al., *CLRS Algorithmic Reasoning Benchmark*, ICML 2022. https://arxiv.org/abs/2205.15659
- **[R10]** *CLRS-Text*, 2024. https://arxiv.org/abs/2406.04229
- **[R11]** *Neural Algorithmic Reasoning without Intermediate Supervision*, NeurIPS 2023. https://arxiv.org/abs/2306.13411
- **[R12]** Hao et al., *Reasoning with Language Model is Planning with World Model*, 2023. https://arxiv.org/abs/2305.14992
- **[R13]** Zhou et al., *Language Agent Tree Search*, 2024. https://arxiv.org/abs/2310.04406
- **[R14]** Liu et al., *LLM+P*, 2023. https://arxiv.org/abs/2304.11477
- **[R15]** `doc/research_proposal.md`, local proposal and planner claims.
- **[R16]** `doc/high_level_plans/research_execution_plan.md`, current implementation scope.
- **[R17]** `doc/detailed_implementation_summary/phase3_expert_trajectories_summary.md`, planner semantics and Phase 3 scope.
- **[R18]** `doc/detailed_implementation_summary/phase3_gbfs_replacement.md`, BFS/GBFS drift.

## Instrumentation and convergence

- R1 and R3 are resolved: the method should be central; broad analysis is not required.
- R2 and R4 are partial: the closest-work sweep supports CGAS as a differentiated hypothesis, not a proven priority claim.
- MC4 remains unresolved until experiments run. No performance or causal effectiveness is claimed.
- Convergence: generic routing, tool invocation, process supervision, and modality dropout were closed as insufficient novelty stories. The remaining open question is empirical: whether verifier-derived minimum-cost certificate routing improves the fidelity-cost frontier.
