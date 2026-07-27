# ULW-Research Synthesis: LLM Planning and Search

Workers: 2 · Waves: 2 · Sources: 12 primary/official · Verifications: 0 code executions

## Executive Summary

The literature already establishes the component ideas behind the proposal: LM-only tree/graph thought search (ToT, GoT), LM-driven MCTS and environment feedback (RAP, LATS), formal-planner delegation through PDDL (LLM+P, LLM-DM), and embodied feedback/affordance grounding (SayCan, Inner Monologue). The local system should not claim any of those mechanisms as novel.

The defensible contribution is an empirical integration: train/evaluate from replay-validated PDDL state/action traces across a classical-planner portfolio, attach rendered Planimation state images, retain trace-fidelity/provenance, and externalize validated search state. No retrieved primary source combines all of these, but that negative result remains a bounded search finding rather than proof of priority. The local repository does not yet establish that this combination improves planning, so no performance/causal novelty claim is supported.

## Findings by Theme

### LM Deliberation and Search

- RAP, *Reasoning with Language Model is Planning with World Model* (2023), uses an LM as world model/policy in MCTS and task-specific rewards. It is inference-time prompting and evaluates reasoning/planning tasks. [Source 1]
- ToT, *Tree of Thoughts* (2023), searches LM-generated text thoughts with LM value/vote evaluation and BFS/DFS; it is text-only prompt-time search. [Source 2]
- GoT, *Graph of Thoughts* (2024), permits dependency graphs, aggregation, refinement, and feedback loops among text thoughts. [Source 3]
- LATS, *Language Agent Tree Search* (2023), applies MCTS to acting trajectories with environment feedback and reflection. [Source 4]

Implication: the proposal can borrow a tree/graph controller, but must distinguish deterministic PDDL successor/replay checks from learned or language-based state/reward prediction.

### Formal Planning Integration

- LLM+P (2023) translates natural language to PDDL, solves through a classical planner, then translates the answer back. [Source 5]
- LLM-DM (2023) builds/corrects a PDDL domain model using validator/human feedback and invokes sound domain-independent planners. [Source 6]
- PlanBench (2022) provides automated-planning-style benchmark domains for plan generation and reasoning about change. [Source 7]

Implication: PDDL plus a planner is prior art. The proposal must locate its contribution in trace-level supervision/fidelity and controlled visual state conditioning, not in calling a planner.

### Embodied and Multimodal Grounding

- SayCan (2022) combines LM likelihood with learned robot-skill affordance values. [Source 8]
- Inner Monologue (2022) feeds closed-loop textual environment feedback into an LM planner. [Source 9]
- ALFWorld (2020) links text policies to visually grounded execution. [Source 10]

Implication: visual/embodied grounding is not new. A credible experiment needs matched text/image information, image-alignment checks, replay validity, and visual corruption/renderer-transfer controls.

## Codebase Findings

The local proposal requires Planimation image supervision, GBFS full trace capture, FF/IW/Graphplan replay validation with `success_plan_replayed` fidelity labels, and portable provenance: `.omo/plans/complete-phase-3-supervised-data.md`. The README identifies raw planner traces as a context-window risk and recommends externalizing frontier, visited, novelty, mutex, and planning-graph state: `README.md:19-21`.

## Sources

1. https://arxiv.org/abs/2305.14992 — RAP, 2023. Primary.
2. https://arxiv.org/abs/2305.10601 — ToT, 2023. Primary; official code: https://github.com/princeton-nlp/tree-of-thought-llm/tree/8050e67d0e3a0fddc424d7fa5801538722a4c4cc.
3. https://arxiv.org/abs/2308.09687 — GoT, 2024. Primary; official code: https://github.com/spcl/graph-of-thoughts/tree/3d9d9dbd8937d47a4441f681b8b40e3c5b054f16.
4. https://arxiv.org/abs/2310.04406 — LATS, 2023. Primary.
5. https://arxiv.org/abs/2304.11477 — LLM+P, 2023. Primary.
6. https://arxiv.org/abs/2305.14909 — LLM-DM, 2023. Primary.
7. https://arxiv.org/abs/2206.10498 — PlanBench, 2022. Primary.
8. https://arxiv.org/abs/2204.01691 — SayCan, 2022. Primary.
9. https://arxiv.org/abs/2207.05608 — Inner Monologue, 2022. Primary.
10. https://arxiv.org/abs/2010.03768 — ALFWorld, 2020. Primary.
11. https://arxiv.org/abs/2305.16291 — Voyager, 2023. Primary.
12. https://arxiv.org/abs/2308.10379 — Algorithm of Thoughts, 2023. Primary.

## Verified Claims

All asserted literature claims are normal-risk primary-source claims C5-C12 from `claim-graph.md`. There are no executed-code verification artifacts. C13 is unresolved and is not asserted as a novelty fact.

## Contradictions

The local plan describes a target multimodal/replay-validated study; current repository evidence does not demonstrate an end-to-end model result. This changes the novelty framing from demonstrated result to testable experimental design.

## Gaps

No source proves global absence of the combined approach. `R*` nomenclature is ambiguous and excluded. A systematic citation search for PDDL trace learning with FF/IW/Graphplan and controlled image conditioning remains prudent before publication.

## Expansion Trace

Wave 1: dedicated RAP/world-model and ToT/GoT workers retrieved primary papers and official implementations. Wave 2: counter-search retrieved PlanBench, ALFWorld, LLM-DM, and visual/formal-adjacent literature. Convergence was reached for this delegated bounded memo after leads either resolved into sources or were excluded as ambiguous; residual global-absence claim is explicitly unresolved.
