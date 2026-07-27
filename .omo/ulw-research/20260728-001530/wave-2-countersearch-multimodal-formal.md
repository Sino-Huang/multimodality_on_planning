# Wave 2: Counter-search for Multimodal Formal Planning

Distinct searches used: `multimodal PDDL planning`; `vision-language formal planning`; `PlanBench`; `ALFWorld`; and exact primary-source retrieval for PlanBench, ALFWorld, SayCan, Inner Monologue, Voyager, RAP, ToT, GoT, LATS, Algorithm of Thoughts, LLM+P, and LLM-DM.

Results: PlanBench (https://arxiv.org/abs/2206.10498) tests formal planning/reasoning about change and reports poor native LLM planning. ALFWorld (https://arxiv.org/abs/2010.03768) aligns text policies with grounded visual execution. LLM-DM (https://arxiv.org/abs/2305.14909) builds/corrects PDDL world models then solves with sound domain-independent planners. Search recovered visual/formal components separately but no direct source that jointly evaluates rendered state supervision, replay-validated trace learning, and a GBFS/FF/IW/Graphplan portfolio. This is an absence-of-evidence statement, not a novelty proof.
