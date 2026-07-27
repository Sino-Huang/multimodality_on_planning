# Wave 1: RAP and World-Model Planning

Worker completed twelve distinct query angles. Primary sources: RAP (2023, https://arxiv.org/abs/2305.14992), LATS (2023, https://arxiv.org/abs/2310.04406), LLM+P (2023, https://arxiv.org/abs/2304.11477), SayCan (2022, https://arxiv.org/abs/2204.01691), Inner Monologue (2022, https://arxiv.org/abs/2207.05608), Voyager (2023, https://arxiv.org/abs/2305.16291), and Reflexion (2023, https://arxiv.org/abs/2303.11366).

Key findings: RAP uses an LM as policy/world model in MCTS with task rewards; LATS adds environment feedback and reflection to MCTS over agent trajectories; LLM+P delegates PDDL to a classical planner. None supplies the local proposal's combined replay-validated PDDL traces, Planimation images, multiple classical planner families, and validated external-memory design.

Verbatim expansion lead: `R*` naming is ambiguous; process-reward/verifier-guided test-time scaling may overlap reward guidance.
