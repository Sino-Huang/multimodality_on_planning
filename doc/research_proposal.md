# Certificate-Guided Adaptive Scaffolding for Multimodal Search Planning

**ICLR 2027 Research Proposal**  
*A method for allocating bounded planning support when a multimodal planner cannot maintain a valid search state*

---

## 1. Abstract

Multimodal planners frequently solve short planning instances but fail when a search state must be preserved across a long horizon. Giving every step an external scratchpad, a long chain of thought, or additional modality tokens can improve fidelity, but it also increases cost and can introduce irrelevant or conflicting information. Existing process-supervision, adaptive-computation, modality-routing, and tool-use methods do not answer a planning-specific question: **when does a next search-state update require structured support, and what is the least costly support that makes it valid?**

We propose **Certificate-Guided Adaptive Scaffolding (CGAS)**. A planner predicts a compact, typed search certificate together with its next action. A lightweight controller selects one of three bounded supports: direct decoding, a compact prior-certificate delta, or a state-keyed external-memory operation. An executable planner verifier supplies counterfactual training labels: the minimum-cost support that yields a valid next certificate transition. CGAS therefore learns from planner invariants rather than free-form rationales, confidence alone, or a fixed tool template.

The primary evaluation studies stateful search with Breadth-First Search (BFS) and Iterated Width (IW), where FIFO/visited and novelty invariants are precise. We compare CGAS against direct vision-language planning, always-on certificate support, always-on memory, a parameter-matched confidence router, uniform process supervision, and robust-fusion baselines. The main outcome is verifier-checked structural fidelity under a resource budget, measured on longer, wider, and compositionally held-out planning instances. Fast Forward (FF) and Graphplan are secondary generalization settings once their trace semantics are exact or clearly labelled as approximations.

The paper is method-centered. A small calibration study identifies the dominant certificate failures and fixes the scaffold palette before the main experiment. Attention analysis is not a contribution; at most, one targeted controller ablation tests whether certificate information, rather than generic routing capacity, causes the improvement.

---

## 2. Problem Setting

Let a planner observe a planning state `x_t` through a fixed multimodal interface and predict an action `a_t` plus a planner-specific certificate `c_t`. A certificate records the minimum structured state needed to verify the current search update. Let `V_a(c_t, c_{t+1}, x_t)` be an executable verifier for algorithm family `a`.

The planner may choose a scaffold `s_t` from the fixed palette:

| Scaffold | Cost | Meaning |
|---|---:|---|
| `direct` | 0 | Predict action and certificate from the fixed VLA observation. |
| `certificate` | low | Read a bounded, prior verifier-approved certificate and write a delta. |
| `memory` | higher | Retrieve or update a bounded, state-keyed external certificate store. |

CGAS learns a policy `pi_phi(s_t | x_t, c_hat_t, h_t)` and an action/certificate predictor. The primary objective is:

`L = L_action + lambda_c L_certificate + lambda_s L_route + lambda_cost cost(s_t)`.

`L_route` is supervised with a counterfactual minimum-cost label: among permitted scaffolds, choose the least costly one that allows a verifier-valid transition. During inference, the controller sees only model predictions, bounded prior certificates, and live tool results. It never receives a gold queue, novelty table, or oracle planner trace.

This scope avoids an unidentifiable claim that a modality is intrinsically necessary for a classical algorithm. The fixed VLA observation is held constant in the core study; CGAS allocates structured support, not task information.

---

## 3. Research Gap and Novelty Positioning

### 3.1 What prior work already establishes

| Area | Representative work | Established result | Why it is insufficient for this proposal |
|---|---|---|---|
| Neural algorithmic reasoning | Neural execution of graph algorithms [1]; CLRS [2]; CLRS-Text [3] | Intermediate algorithm states and structural OOD evaluation are established. | They do not learn a minimum-cost support policy over executable PDDL search certificates. |
| Process supervision and planning trajectories | Let's Verify Step by Step [4]; planning-based reasoning with synthesized process rewards [5] | Step-level objectives and trajectory ranking can improve reasoning. | They do not label the least scaffold required to make a specific search transition valid. |
| Adaptive reasoning | Adaptive computation [6]; differentiable adaptive computation for visual reasoning [7] | Models can adapt computation depth to instance difficulty. | CGAS routes based on a verifier-defined invariant and explicit scaffold cost, not only difficulty or halting. |
| Multimodal routing and tool use | Modality dropout [8]; SMIL [9]; BEE [10] | Robust fusion, missing-modality learning, and self-regulated tool invocation are active directions. | CGAS is not a generic modality gate or a tool-usage reward. Its labels are counterfactual planner-certificate transitions. |
| LLM planning | RAP [11]; LATS [12]; LLM+P [13] | Language models can use search, feedback, and PDDL/classical planners. | These systems do not study a learned, cost-aware policy for preserving verified search state in multimodal planning. |

### 3.2 Research gap

No work identified in the review jointly provides all of the following: (1) compact, planner-specific certificates with executable transition checks; (2) counterfactual labels for the minimum-cost scaffold needed at a step; (3) learned selection between direct decoding, bounded certificate context, and live external memory; and (4) evaluation of the fidelity-cost trade-off under structural planning shifts. This is a gap statement, not a priority proof. The paper will use the bounded phrase **"to our knowledge"** and repeat the closest-work search before submission.

### 3.3 Novelty claim

The proposed novelty is not multimodal planning, algorithm traces, external memory, or adaptive routing in isolation. It is the **combination of verifier-derived counterfactual certificate supervision and minimum-cost scaffold selection for search planning**.

---

## 4. Research Questions

### RQ1: Can a verifier-derived support policy improve the fidelity-cost frontier?

Does CGAS achieve higher verified certificate fidelity and structural planning success than direct VLA planning while using less support than always-on memory?

### RQ2: Does counterfactual certificate supervision outperform generic routing and process supervision?

Does the CGAS route objective outperform a parameter-matched confidence router, uniform certificate supervision, and trajectory/process-reward baselines at matched backbone and support budget?

### RQ3: When does multimodal context remain insufficient?

Which certificate invariant, horizon, branching factor, and observation corruption trigger scaffolding? This is a compact calibration analysis that motivates the method; it is not a claim about universal modality affordances.

### RQ4: Does the method transfer across planner families?

After validating BFS and IW, can the same scaffold policy and counterfactual-generation recipe improve FF and Graphplan-style traces whose semantics have been precisely defined?

---

## 5. Method

### 5.1 Typed search certificates

The certificate is a compact target, not a natural-language explanation.

| Family | Primary status | Certificate fields | Verifier invariant |
|---|---|---|---|
| BFS | Core | frontier head/order summary, visited-set delta, expanded state | FIFO order, legal successors, monotonic visited set |
| IW | Core | novelty tuple, seen-feature delta, width decision | novelty membership and valid width transition |
| FF | Secondary | declared relaxed-goal support and heuristic choice | exact documented approximation and legal selected action |
| Graphplan | Secondary | proposition/action-layer delta and mutex witness | valid layer construction, mutex semantics, plan extraction replay |

The existing repository must reconcile historical BFS data with the active GBFS pipeline before a dataset is used for CGAS. FF and Graphplan must be called approximations if their current local emitters are not canonical implementations.

### 5.2 Counterfactual supervision

For each expert transition, data generation emits:

1. The valid next certificate and action.
2. Minimally invalid certificate variants, each violating one named invariant while holding the task state fixed.
3. The set of permitted scaffolds and their measured token/tool cost.
4. The minimum-cost scaffold that restores verifier validity.

Counterfactuals are generated by planner code, not by an LLM. Examples include a FIFO-versus-LIFO frontier update, an omitted visited-state delta, or a novelty tuple already observed. The generator must reject variants that change more than one invariant, so the route label remains interpretable.

### 5.3 Bounded external memory

Memory is an environment-owned, state-keyed store with `read`, `append`, `replace`, and `delete` operations. It stores only model predictions or prior verifier-approved certificate entries. The interface logs every operation, returned byte count, and latency. CGAS is compared to an always-on memory baseline with the same storage, operations, and budget.

### 5.4 Compact calibration phase

Before the main run, train a small direct VLA baseline on short BFS/IW traces. On held-out instances, identify the first failed certificate invariant. Freeze the certificate schema, scaffold palette, costs, and route-label generator before CGAS training. The paper reports only:

- a first-failure matrix by family and structural difficulty;
- a route-calibration curve; and
- one controller ablation that removes certificate inputs.

Attention maps are optional appendix evidence and cannot by themselves support a causal claim.

---

## 6. Experimental Design

### 6.1 Core task and controls

The core task uses Blocksworld with matched image and language observations. In the primary experiment, raw VLA context, backbone, action vocabulary, training examples, and context budget are fixed across all methods. This isolates structured support selection from changes in task information.

The data split varies:

- object count and plan horizon;
- branching factor and frontier size;
- compositional initial/goal arrangements;
- object names and render style; and
- observation corruption or removal as secondary stress tests.

### 6.2 Baselines

1. Direct VLA planner with no scaffold.
2. VLA with always-on compact certificate context.
3. VLA with always-on external memory.
4. Parameter-matched confidence or entropy router using the same scaffold palette.
5. Uniform action-plus-certificate supervision.
6. A process-supervision or trajectory-ranking comparator where feasible.
7. A robust-fusion or modality-dropout comparator for multimodal stress tests.

### 6.3 Primary outcomes

| Outcome | Definition |
|---|---|
| Verified certificate fidelity | Fraction of step transitions accepted by the planner verifier. |
| Valid-plan success | Fraction of rollouts reaching the goal with legal actions. |
| Structural OOD fidelity | Certificate fidelity on held-out horizon, object count, and branching grids. |
| Scaffold cost | Tool calls, retrieved/written certificate bytes, extra tokens, and latency. |
| Route optimality | Fraction of choices matching the oracle minimum-cost valid scaffold label. |

The primary claim requires a fidelity-cost frontier: CGAS must improve structural OOD fidelity over direct VLA and use less support than always-on memory at comparable fidelity. Final task success alone is not enough.

### 6.4 Statistical protocol

Use at least five training seeds when compute permits. Report instance-level bootstrap intervals, seed variation, and matched-cost curves. Pre-register primary comparisons before the main run. The calibration set must not overlap with the structural OOD test set.

---

## 7. Scope and Priorities

| Priority | Scope | Role |
|---|---|---|
| P0 | Semantic trace audit, aligned renders, live memory interface, BFS/IW certificate verifier | Required infrastructure |
| P1 | Direct/always-on/router/CGAS comparison on BFS and IW | Main paper result |
| P2 | FF and Graphplan-style transfer after semantics are validated | Generalization evidence |
| P3 | Vision-only/language-only stress tests and continuous domains | Secondary analysis |
| P4 | Cross-task transfer | Follow-on only, not a required ICLR claim |

The proposal does not claim that a specific modality is universally necessary, that attention explains the method, or that planning biases transfer outside planning. Those questions remain possible extensions after CGAS is established.

---

## 8. Risks and Falsification

| Risk | Interpretation | Response |
|---|---|---|
| CGAS matches always-on memory at equal cost | Adaptive policy adds no value. | Report the negative result; simplify the paper to bounded-memory process fidelity or stop the method line. |
| Confidence routing matches CGAS | Certificate counterfactuals are not the causal contribution. | Diagnose label quality; do not claim method novelty without a separation. |
| Counterfactual certificates do not transfer to OOD | The generator is too narrow. | Redesign the certificate schema before the main run. |
| Current traces are semantically inconsistent | Dataset cannot support verifier-derived labels. | Reconcile planner versions and regenerate the affected corpus. |
| Visual context adds no effect | The method can still be a structured-planning method. | Narrow the claim; do not present a multimodal advantage. |

---

## 9. Milestones

| Stage | Deliverable | Decision gate |
|---|---|---|
| 1. Trace readiness | Versioned BFS/IW traces, aligned images, semantic verifier | Every emitted core trace validates. |
| 2. Calibration | First-failure matrix and frozen scaffold palette | At least one recurrent, certificate-localized failure exists. |
| 3. Method run | CGAS and matched baselines across five seeds | CGAS separates from direct and always-on baselines on fidelity-cost. |
| 4. Generalization | Structural OOD grid and optional FF/Graphplan transfer | Main result remains after distribution shift. |
| 5. Paper | Method, counterfactual generator, and bounded analysis | No claim exceeds the executed evidence. |

---

## 10. Contributions

1. **Method:** Certificate-Guided Adaptive Scaffolding, a cost-aware controller over bounded planning support.
2. **Supervision:** Counterfactual minimum-cost labels generated by an executable planner verifier.
3. **Evaluation:** A fidelity-cost protocol for structural planning that separates valid search-state updates from final task success.
4. **Analysis:** A compact calibration study explaining when fixed multimodal context is insufficient, without making attention analysis a headline claim.

## 11. One-Sentence Pitch

> **CGAS teaches a multimodal planner to request the least costly structured support needed to keep its search state valid.**

---

## References

[1] Veličković, P. et al. Neural Execution of Graph Algorithms. ICLR, 2020. https://arxiv.org/abs/1910.10593

[2] Veličković, P. et al. The CLRS Algorithmic Reasoning Benchmark. ICML, 2022. https://arxiv.org/abs/2205.15659

[3] CLRS-Text. 2024. https://arxiv.org/abs/2406.04229

[4] Lightman, H. et al. Let's Verify Step by Step. 2023. https://arxiv.org/abs/2305.20050

[5] Jiao, F. et al. Learning Planning-based Reasoning by Trajectories Collection and Process Reward Synthesizing. EMNLP, 2024. https://arxiv.org/abs/2402.00658

[6] Neumann, M., Stenetorp, P., and Riedel, S. Learning to Reason With Adaptive Computation. 2016. https://arxiv.org/abs/1610.07647

[7] Figurnov, M. et al. Differentiable Adaptive Computation Time for Visual Reasoning. CVPR, 2020. https://doi.org/10.1109/CVPR42600.2020.01283

[8] Maheshwari, A. and Sarcar, S. Learnable Irrelevant Modality Dropout for Multimodal Action Recognition. CVPR, 2022. https://doi.org/10.1109/CVPR52688.2022.01957

[9] Zhao, Y. et al. SMIL: Multimodal Learning with Severely Missing Modality. AAAI, 2021. https://doi.org/10.1609/aaai.v35i3.16330

[10] Chen, X. et al. Beyond the Eye: Efficient Multimodal Reasoning via Self-Regulated Implicit Visual Tools. 2026. https://arxiv.org/abs/2607.11106

[11] Hao, S. et al. Reasoning with Language Model is Planning with World Model. 2023. https://arxiv.org/abs/2305.14992

[12] Zhou, A. et al. Language Agent Tree Search. 2024. https://arxiv.org/abs/2310.04406

[13] Liu, B. et al. LLM+P: Empowering Large Language Models with Optimal Planning Proficiency. 2023. https://arxiv.org/abs/2304.11477
