# Wave 1: Online Method Search

Observed 2026-07-28. Primary sources and full-page/metadata checks were used where available.

## Findings

- Generic process supervision and trajectory-ranking interventions are already active research areas. Jiao et al. learn planning-based reasoning from collected trajectories ranked by synthesized process rewards through DPO; a generic process-reward method is not a sufficient contribution.
- Adaptive computation is established, including adaptive inference-step learning and differentiable adaptive computation for visual reasoning. A method cannot claim novelty merely for deciding when to think more.
- Recent multimodal systems already learn self-regulated tool invocation. BEE (2026) introduces structured tool slots and a reward that penalizes ineffective implicit visual-tool use. A generic modality or tool gate is therefore too close.
- Multimodal missing-modality, modality dropout, and privileged-modality methods establish that robust fusion and routing are not new. The opportunity is a routing criterion defined by **planner-executable invariants**, rather than confidence, image quality, or missingness.

## Sources

1. Jiao et al., *Learning Planning-based Reasoning by Trajectories Collection and Process Reward Synthesizing*, EMNLP 2024. https://arxiv.org/abs/2402.00658
2. Neumann et al., *Learning to Reason With Adaptive Computation*, 2016. https://arxiv.org/abs/1610.07647
3. Figurnov et al., *Differentiable Adaptive Computation Time for Visual Reasoning*, CVPR 2020. https://doi.org/10.1109/CVPR42600.2020.01283
4. Chen et al., *Beyond the Eye: Efficient Multimodal Reasoning via Self-Regulated Implicit Visual Tools*, 2026. https://arxiv.org/abs/2607.11106
5. Maheshwari and Sarcar, *Learnable Irrelevant Modality Dropout for Multimodal Action Recognition*, CVPR 2022. https://doi.org/10.1109/CVPR52688.2022.01957
6. Zhao et al., *SMIL: Multimodal Learning with Severely Missing Modality*, AAAI 2021. https://doi.org/10.1609/aaai.v35i3.16330
7. Zhu et al., *Unbiased Missing-Modality Multimodal Learning*, ICCV 2025. https://doi.org/10.1109/ICCV51701.2025.02272

## Method implication

The viable method must be specific: route among planning scaffolds using a predicted and executable search certificate, impose a cost for unnecessary scaffolding, and optimize state-transition fidelity. It must be evaluated against always-on memory, no memory, generic confidence routing, process reward/ranking, and modality dropout.

## EXPAND

none — generic adaptive-routing novelty is closed as a dead end; the certificate-guided formulation is retained as the new hypothesis.
