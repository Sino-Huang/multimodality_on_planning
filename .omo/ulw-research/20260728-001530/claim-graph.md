# Claim Graph

## Verified Claims

None yet. Only claims entering this allowlist after primary-source and counter-search review may appear as high-risk assertions in the synthesis.

## Nodes

| claim_id | Statement | claim type | risk tier | scope | intent ids | supporting observations | contradicting observations | independent observation groups | convergence status | counter-search result | primary source backing | dependencies | status | final synthesis location |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | The proposal uses replay-validated PDDL plans/traces as supervision. | local fact | normal | proposal | I1 | O1 | none | local-plan | supported | n/a | yes | none | supported | pending |
| C2 | The proposal has vision supervision from Planimation frames. | local fact | normal | proposal | I1 | O1 | none | local-plan | supported | n/a | yes | none | supported | pending |
| C3 | The proposal separates full traces from replay-only trace fidelity. | local fact | normal | proposal | I1 | O1 | none | local-plan | supported | n/a | yes | none | supported | pending |
| C4 | The proposal recommends external memory for search state to control context length. | local fact | normal | proposal | I3 | O2 | none | local-readme | supported | n/a | yes | none | supported | pending |
| C5 | RAP uses language-model transition/reward predictions in MCTS-style reasoning search. | literature fact | normal | RAP | I1 | O3 | none | arXiv primary | supported | ToT/LATS use different search variants, not a refutation | https://arxiv.org/abs/2305.14992 | none | supported | Findings/RAP |
| C6 | ToT uses LM-generated/evaluated text thoughts in BFS/DFS, without core parameter training. | literature fact | normal | ToT | I1 | O4 | none | arXiv + official repository | supported | No contrary core-method source found | https://arxiv.org/abs/2305.10601 | none | supported | Findings/ToT |
| C7 | GoT represents text thought states as an arbitrary dependency graph with aggregation/refinement feedback. | literature fact | normal | GoT | I1 | O5 | none | arXiv + official repository | supported | No contrary core-method source found | https://arxiv.org/abs/2308.09687 | none | supported | Findings/GoT |
| C8 | LATS applies MCTS over agent trajectories with environment feedback and LM reflection. | literature fact | normal | LATS | I1 | O6 | none | arXiv primary | supported | No contrary core-method source found | https://arxiv.org/abs/2310.04406 | none | supported | Findings/LATS |
| C9 | LLM+P translates natural language to PDDL and delegates solving to a classical planner. | literature fact | normal | formal integration | I1 | O7 | none | arXiv primary | supported | LLM-DM has a different world-model construction focus | https://arxiv.org/abs/2304.11477 | none | supported | Findings/LLM+P |
| C10 | LLM-DM uses an LLM to construct/correct a PDDL domain model and sound planners to solve it. | literature fact | normal | formal integration | I1 | O8 | none | arXiv primary | supported | No contrary core-method source found | https://arxiv.org/abs/2305.14909 | none | supported | Findings/LLM-DM |
| C11 | SayCan and Inner Monologue supply embodied feedback/affordance grounding but not PDDL replay certification. | literature fact | normal | embodied planning | I1 | O9, O10 | none | two arXiv primary sources | supported | No counterexample in method descriptions | https://arxiv.org/abs/2204.01691; https://arxiv.org/abs/2207.05608 | none | supported | Findings/Embodied |
| C12 | PlanBench is a formal-planning benchmark designed to test plan generation and reasoning about change. | literature fact | normal | benchmark | I1 | O11 | none | arXiv primary | supported | No contrary core-method source found | https://arxiv.org/abs/2206.10498 | none | supported | Findings/Benchmarks |
| C13 | No retrieved primary source combines rendered symbolic state images, replay-validated trace supervision, and a GBFS/FF/IW/Graphplan planner portfolio. | literature synthesis | high | novelty | I1, I2 | O3-O12 | none found | independent query lanes; single-source exception not applicable | partial | Explicit multimodal-PDDL counter-search found adjacent components only | none | Depends on bounded search coverage | unresolved | Gaps/Novelty |
