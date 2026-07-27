# Wave 2: LLM Planning and Search Expansion

## Key findings

- RAP uses an LM as policy and world model in MCTS-style planning; ToT/GoT conduct text-only tree/graph inference-time search.
- LATS combines tree search, environment feedback, and reflection; LLM+P translates language into PDDL and delegates search to a classical planner.
- These precedents eliminate any component-level novelty claim around planning, tree search, tool/environment feedback, PDDL, or external memory.
- The remaining defensible contribution is a bounded causal study: replay-validated planner traces, information-equated visual/text/memory conditions, planner-family process metrics, and diagnosis-driven repair.

## Primary sources

1. Hao et al., *Reasoning with Language Model is Planning with World Model*, 2023. https://arxiv.org/abs/2305.14992
2. Yao et al., *Tree of Thoughts*, 2023. https://arxiv.org/abs/2305.10601
3. Besta et al., *Graph of Thoughts*, 2023. https://arxiv.org/abs/2308.09687
4. Zhou et al., *Language Agent Tree Search*, 2024. https://arxiv.org/abs/2310.04406
5. Liu et al., *LLM+P*, 2023. https://arxiv.org/abs/2304.11477

## EXPAND

none — the resulting absence-of-combination claim remains explicitly unresolved rather than asserted as priority.
