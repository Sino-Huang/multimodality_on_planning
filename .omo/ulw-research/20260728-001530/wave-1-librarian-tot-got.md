# Wave 1: ToT and GoT

Primary sources: Tree of Thoughts (2023, https://arxiv.org/abs/2305.10601) and Graph of Thoughts (2024, https://arxiv.org/abs/2308.09687). Official implementations were checked at ToT `8050e67d0e3a0fddc424d7fa5801538722a4c4cc` and GoT `3d9d9dbd8937d47a4441f681b8b40e3c5b054f16`.

ToT is inference-time language-thought BFS/DFS with LM proposal and evaluation. GoT generalizes to an arbitrary thought graph with merge/refine/feedback operations. Both are text-centric and do not use PDDL legality, images, simulator actions, or trace replay. The useful import for the proposal is controller/search structure, not its claimed grounding contribution.

Verbatim expansion result: `none — primary papers, official repositories, README, arXiv HTML, API metadata, and pinned repository commits were retrieved.`
