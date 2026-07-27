# ULW-Research Synthesis: ICLR 2027 Novelty Assessment

Workers: 4 completed evidence lanes · Waves: 3 (local audit and two literature expansions) · Sources: 23 primary/local sources · Verifications: local source and implementation audit; no model experiment has been run

## Executive summary

**Verdict: potentially ICLR-novel, but not on the current headline.** Training a model on search trajectories, measuring systematic generalization, using a curriculum, or attaching a scratchpad are established directions in neural algorithmic reasoning and language-model reasoning [S1-S14]. The novelty that can survive review is a **controlled causal experiment on which computational resource interface changes the *executed search process***, across planner families, with a mechanism-validated, low-cost repair. This is narrower, more empirical, and stronger than the present claim that vision, language, and tools each natively afford a particular classical planner.

The project has real infrastructure for symbolic planning data, traces, and rendering. It does **not** currently have a trained planner, live tool runtime, aligned visual training condition, semantic execution evaluator, or a dataset that supports the declared four-family comparison [S15-S18]. Thus no paper or internal presentation should imply existing VLM, attention, transfer, or CRSH results. The next result-worthy milestone is a pre-registered Blocksworld resource-factorial pilot with real images, live tool calls, transition-level fidelity scoring, and held-out structural scales.

## Novelty assessment

| Literature area | What is already established | What this paper must add |
|---|---|---|
| Neural algorithmic reasoning | Intermediate execution supervision, BFS-like neural execution, and size OOD are central to NAR and CLRS [S1-S3]. | PDDL planner-family traces under controlled resource interfaces, not generic trace learning. |
| Language models on algorithm traces | CLRS-Text serializes algorithm traces for LM fine-tuning [S4]. | Information-equated visual/text/tool conditions and an executed trace metric. |
| Process supervision | Step-level supervision is established; output-only NAR can be competitive [S7-S9]. | Trace vs outcome-only vs verifier-labelled process supervision as a required ablation. |
| Prompt/search/tool reasoning | CoT, least-to-most, planning/search, and external computation are established [S5-S6, S10-S12]. | A **live, budget-matched memory interface** whose causal effect is measured, not a static oracle scratchpad. |
| LM planning systems | RAP, ToT/GoT, LATS, and LLM+P respectively cover LM-MCTS, thought search, environment feedback, and PDDL plus classical planning [S19-S23]. | A bounded resource-interface experiment with replay-validated process metrics and a causal repair, not a new planning-system assembly. |
| Systematic generalization | Architecture, serial token budget, and training details materially change OOD behavior [S11-S14]. | Object-count, branching, depth, predicate-composition, renderer, and modality-corruption OOD grids. |

### Claim that is supportable

> Under fixed model, data budget, and task information, does the *resource interface* (visual, linguistic, external memory) interact with the target search computation to change its learnability and failure mode? Can a mechanistically diagnosed, low-cost repair remove the resulting failure?

This is a causal-science question, not an ablation question, because its primary estimand is an algorithm-by-resource interaction on **verified internal search state transitions**. The novelty remains contingent: the search found no single work jointly varying visual/text/external-memory interfaces across BFS, FF, IW, and Graphplan under that protocol, but literature search cannot prove absence [S1-S14]. Write “to our knowledge,” then maintain a closest-work appendix.

### Claims to remove or soften

- Do not say transformers are architecturally unable to execute BFS without a tool. Looped-transformer constructions and CoT serial computation make an absolute claim false [S11-S12]. State a bounded hypothesis: “under this backbone, inference budget, and interface.”
- Do not say vision “naturally learns Fast Forward” or language “naturally learns Graphplan.” These are testable directional hypotheses, not literature-backed facts.
- Do not call attention patterns an explanation. Attention is not a causal explanation by itself [S10].
- Do not claim that trace SFT is necessary for structural generalization. It must beat outcome-only and latent-process alternatives [S7-S8].
- Do not lead with cross-task bias transfer. It is expensive, weakly specified, and currently unimplemented. Make it a contingent extension after the within-domain causal story succeeds.

## The ICLR story

### Recommended title and pitch

**Title:** *When Does a Modality Change How a Model Searches? Resource Interfaces for Structural Planning*

**One-sentence pitch:** *Information-equated vision, language, and external memory do not merely change planning accuracy: they selectively change which search invariants a model can execute, and those failures can be diagnosed and repaired with a small targeted objective.*

### Three contributions, in the required causal order

1. **A resource-factorial benchmark for structural planning.** All eight resource subsets of `{V, L, T}` across planner families, with equalized information, token/compute budget, a real tool API, and an executable trace verifier.
2. **An empirical interaction law.** Estimate `resource subset x search family x structural scale`, separating task success from FIFO/visited, novelty, heuristic, and mutex invariants. Report both help and degradation as interactions, not anecdotes.
3. **Failure-to-fix mechanism.** Establish one causal chain: resource perturbation -> decodable search-state failure -> causal component intervention -> lightweight repair -> OOD improvement. This is the differentiator that turns a benchmark into a paper.

The cognitive framing can remain in the motivation, but CRSH should be an operational hypothesis. Define `M(S, a | model, data, budget)` for every `S` subset, not `M(r,a)`. A hard boundary is only a rejected/retained hypothesis under a named model and budget; it is not a property of “vision” or “language” in general.

## Experimental design that can support the story

### 1. Treatment and controls

Run all `V/L/T` subsets: none, V, L, T, V+L, V+T, L+T, V+L+T. The current four arms omit three required subsets and cannot identify tool necessity or compensation [S15].

- **Information equality:** Render the same symbolic state into images and a canonical language description; audit every arm for leaked action lists, PDDL, state IDs, and latent symbolic encodings. Match token length, context window, action vocabulary, and total inference compute.
- **Real tools:** `read`, `append`, `replace`, `delete`, and `query` calls must operate on an environment-owned store. Match write count, bytes, latency, and scratchpad budget. Include a no-op tool and an equal-token CoT scratchpad control.
- **Two training regimes:** (a) *named execution*, which evaluates faithful execution of a supplied algorithm, and (b) *algorithm choice*, which hides the family label and asks the model to solve instances while the verifier classifies its trajectory. The former cannot establish “native convergence” by itself [S15].
- **Planner semantics:** Either implement canonical BFS/FF/IW/Graphplan or rename approximations precisely. Keep BFS and GBFS separate. The existing materials mix the two and label FF/Graphplan approximations [S16-S18].

### 2. Structural outcomes

Primary outcome: **verified algorithmic fidelity**, not response keywords or final success. For every rollout, an oracle checks legal transitions and the relevant state invariant:

- BFS: FIFO frontier, visited-set updates, no prohibited duplicate expansion.
- IW: novelty-table membership and width transition.
- FF: explicitly specified relaxed-plan/heuristic approximation and greedy choice.
- Graphplan: proposition/action layers, mutex validity, and extraction/replay.

Secondary outcomes: solved rate, valid-plan rate, sample efficiency, tool-call cost, wall time, and first-failure category. Use held-out grids for object count, plan length, branching factor, composition/predicate split, object renaming, renderer style, missing/corrupted modality, and tool-budget reduction. Train/evaluate with 5 seeds if feasible, report instance-level bootstrap intervals, and pre-register the primary interactions. Three seeds do not substantiate threshold-like “hard boundary” claims [S15].

Fit a hierarchical model such as `fidelity ~ algorithm * resource_subset * scale + (1|seed) + (1|instance_family)`. Report marginal resource effects and interaction contrasts. Define degradation prospectively: resource `r` degrades at context `S` when `Y(S union {r}) - Y(S) < 0` with its interval excluding zero, after information and budget controls. This lets the paper honestly report negative multimodal transfer rather than assume more modalities should help.

### 3. Attention and mechanism

Use attention as a *measurement candidate*, never the endpoint.

1. Define state variables before inspecting activations: frontier position, visited membership, novelty status, mutex edge, current goal predicate, and tool-read/write provenance.
2. Train layer/head/residual-stream probes on held-out instances. Check that probes predict state variables beyond token position, output logit, or raw modality identity.
3. Measure attention and residual features only after matched visual/text and corrupted-input controls.
4. Test necessity with head/path ablation and modality-token masking; test sufficiency with activation patching between a successful and matched failing trajectory. Re-run the executable verifier, not a language-model proxy.
5. Claim a mechanism only if the same component is predictive, necessary, and its causal restoration rescues the proposed invariant. Otherwise call it a correlate.

This directly answers the user’s attention question while respecting the attention-explanation objection [S10]. The strongest expected result is not “vision head 7 attends to blocks,” but “an intervention on a resource-specific component restores visited-set fidelity under an information-matched counterfactual.”

### 4. Lightweight intervention

Pre-register **Invariant-Gated Process Repair (IGPR)** as the main intervention. It adds no planner module and no new inference tool:

- The existing executable verifier labels the *first violated search invariant* in a trace.
- A small auxiliary loss upweights the corresponding next-state fields only on the failing class: frontier/visited for BFS, novelty slots for IW, relaxed-goal fields for FF, or mutex fields for Graphplan.
- For a demonstrated multimodal conflict, apply modality dropout only to the conflicting resource during those updates and require consistency of the verifier-labelled state transition across equivalent visual/text views.
- Compare against uniform trace SFT, outcome-only, full auxiliary supervision, generic modality dropout, and a parameter-matched adapter.

IGPR is lightweight because it changes target weighting and masking, not the backbone, planner, or tool budget. It has a credible mechanism narrative only when the diagnosis nominates the invariant in advance and the repair selectively improves that invariant, including on structural OOD. If the failure is memory capacity, the appropriate repair is instead a sparse live read/write curriculum, compared with equal-token CoT; do not force a loss-based intervention onto a capacity limitation.

## Practical paper sequence

1. **48-hour falsification pilot:** 2 planner families (BFS, IW), 8 resource subsets, small scale grid, real images/tool, and verifier. Stop or revise if no interaction survives information controls.
2. **Main result:** four precisely defined families, trace/outcome/IGPR comparison, structural OOD grid, five seeds, and preregistration.
3. **Mechanism figure:** one successful causal localization-and-repair chain. Put broad attention heatmaps in the appendix.
4. **Transfer:** run only after the main causal result; phrase as an exploratory replication, not a required headline contribution.

## Local reality and immediate blockers

The documents show mature generation, trace, and rendering work, but Phase 4+ model/training/tool/evaluation work remains future scope [S16]. Current evidence includes unaligned/empty visual smoke paths, static scratchpad packaging, lexical fidelity scoring, a historical BFS-only corpus, and a BFS-to-GBFS pipeline drift [S15-S18]. Treat these as engineering starting points, not experimental evidence.

## Sources

- **[S1]** Veličković et al. *Neural Execution of Graph Algorithms*. ICLR 2020. https://arxiv.org/abs/1910.10593
- **[S2]** Veličković et al. *Neural Algorithmic Reasoning*. 2021. https://arxiv.org/abs/2105.02761
- **[S3]** Veličković et al. *CLRS Algorithmic Reasoning Benchmark*. ICML 2022. https://arxiv.org/abs/2205.15659
- **[S4]** *CLRS-Text*. 2024. https://arxiv.org/abs/2406.04229
- **[S5]** Zhou et al. *Least-to-Most Prompting*. 2022. https://arxiv.org/abs/2205.10625
- **[S6]** Laskin et al. *In-context RL with Algorithm Distillation*. 2022. https://arxiv.org/abs/2210.14215
- **[S7]** *Neural Algorithmic Reasoning without Intermediate Supervision*. NeurIPS 2023. https://arxiv.org/abs/2306.13411
- **[S8]** *Neural Algorithmic Reasoning with Causal Regularisation*. 2023. https://arxiv.org/abs/2302.10258
- **[S9]** Lightman et al. *Let's Verify Step by Step*. 2023. https://arxiv.org/abs/2305.20050
- **[S10]** Jain and Wallace. *Attention is not not Explanation*. EMNLP 2019. https://doi.org/10.18653/v1/D19-1002
- **[S11]** *Simulation of Graph Algorithms with Looped Transformers*. 2024. https://arxiv.org/abs/2402.01107
- **[S12]** *Chain of Thought Empowers Transformers to Solve Inherently Serial Problems*. 2024. https://arxiv.org/abs/2402.12875
- **[S13]** *The Devil is in the Detail: Simple Tricks Improve Systematic Generalization of Transformers*. 2021. https://arxiv.org/abs/2108.12284
- **[S14]** *gSCAN: Systematic Generalization in Grounded Language Understanding*. 2021. https://arxiv.org/abs/2109.12243
- **[S15]** Local proposal audit: `doc/research_proposal.md`; `examples/planning_benchmark_slice/zero_shot.py`; `examples/planning_benchmark_slice/modality_serializers.py`.
- **[S16]** Local implementation plan: `doc/high_level_plans/research_execution_plan.md`.
- **[S17]** Local Phase 3 evidence: `doc/detailed_implementation_summary/phase3_expert_trajectories_summary.md`; `phase3_complete_supervised_planning_data_summary.md`; `phase3_gbfs_replacement.md`.
- **[S18]** Local data/render evidence: `doc/detailed_implementation_summary/phase1_planimation_validation_summary.md`; `phase3_hybrid_traversal_rendering_release_evidence_2026-07-15.md`.
- **[S19]** Hao et al. *Reasoning with Language Model is Planning with World Model (RAP)*. 2023. https://arxiv.org/abs/2305.14992
- **[S20]** Yao et al. *Tree of Thoughts*. 2023. https://arxiv.org/abs/2305.10601
- **[S21]** Besta et al. *Graph of Thoughts*. 2023. https://arxiv.org/abs/2308.09687
- **[S22]** Zhou et al. *Language Agent Tree Search*. 2024. https://arxiv.org/abs/2310.04406
- **[S23]** Liu et al. *LLM+P*. 2023. https://arxiv.org/abs/2304.11477

## Instrumentation status

- Intent diff: I1-I5 are partially resolved. The project intent is viable, but the current implementation does not establish the target empirical claims.
- Claim graph: C1/C2/C3/C5/C6/C7 remain unresolved empirical claims; C4 is refuted when stated as generic trace-training novelty and supported only when narrowed to the controlled resource-by-planner study.
- Independent observation: local proposal and execution audits independently converge on the lack of end-to-end experimental evidence. Search-training is an independent literature group.
- Verification economics: no training experiment was executed because the study is not implemented; source-level evidence is the appropriate verification path for this novelty review.
- Cause disappearance: no causal bug was fixed; the attention-as-mechanism overclaim remains open until causal intervention tests exist.
