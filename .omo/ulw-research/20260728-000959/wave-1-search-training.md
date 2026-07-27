# Wave 1: Search-Training Literature

## Key findings

- CLRS supplies algorithmic intermediate supervision and size OOD across 30 algorithm tasks.
- Neural Execution of Graph Algorithms trains neural systems to execute graph-algorithm steps including BFS.
- CLRS-Text serializes algorithm execution traces for language-model fine-tuning.
- NAR Without Intermediate Supervision challenges the claim that intermediate traces are inherently necessary.

## Primary sources

1. Veličković et al., *CLRS Algorithmic Reasoning Benchmark*, ICML 2022. https://arxiv.org/abs/2205.15659
2. Veličković et al., *Neural Execution of Graph Algorithms*, ICLR 2020. https://arxiv.org/abs/1910.10593
3. *CLRS-Text*, 2024. https://arxiv.org/abs/2406.04229
4. *NAR Without Intermediate Supervision*, NeurIPS 2023. https://arxiv.org/abs/2306.13411

## Novelty implication

The paper cannot claim novelty for search-trace training or algorithm learning alone. The defensible gap is a causal, controlled resource-interface comparison across planning algorithm families, accompanied by trace-vs-final-only ablations and structural out-of-distribution evaluation.

## EXPAND

- LEAD: Contrast with multimodal planning and tool-use planning work. WHY: this is the nearest threat to the proposed resource-interface novelty. ANGLE: VLM/VLA planning, external memory, and modality ablations.
