# Research Target Assessment for Supervisor Review

## 1. What I thought the research target was

### My intended target

I understood this project as a proposal to train a vision-language model, not as a study of prompting a language model. I expected the main experiment to train across matched text, rendered-visual, and multimodal conditions, with a curriculum that changes the planning demands presented during training. The scientific question I had in mind was whether the learning signal and the modality of the observation change what the model learns to do.

The distinction I wanted to examine is between local operational competence and structural search competence. Local operational competence includes checking whether an action's preconditions hold and predicting the immediate successor state. Structural search competence includes recognizing landmarks, judging reachability, choosing a path or expansion, and maintaining frontier or search-state information over a long horizon. A model can be good at the former while failing at the latter.

I expected the model to learn to search and return a plan. I did not intend the central contribution to be prediction of the next action in an expert trace followed by concatenation of locally plausible actions. Expert traces can be useful training material, but the target I had in mind requires an observable model contribution to the choices that determine exploration and plan construction.

## 2. Why this target matters

### My motivation from the companion paper

The companion paper, Sukai Huang et al., [*What We Talk About When We Talk About LLM Planning: Evidence for Two Distinct Planning Abilities*](https://arxiv.org/html/2607.11197), arXiv:2607.11197 (2026), provides the motivation for separating these abilities. It studies open-weight text LLMs without task-specific training. Its setting is text-only, rather than visual or multimodal, and it evaluates planning-related subtasks with symbolic checking. ACPBench-Hard contains 1,040 items across eight subtasks. The reported conditions include direct prompting, chain-of-thought, and scratchpad responses, with a symbolic PDDL validator and multidimensional item-response analysis.

The paper reports that a two-dimensional noncompensatory account fits the data better than a one-dimensional account. The two abilities are **operational reasoning** and **structural enumeration**. Operational reasoning covers local tasks such as applicability, progression, and validation. Structural enumeration covers tasks such as reachability, landmark reasoning, and areachability. In the reported analysis, scaling and chain-of-thought help operational reasoning more than structural enumeration. Scratchpad traversal does not remove the structural bottleneck, and output format changes apparent structural performance.

This result motivates a training-and-multimodality study because it identifies a specific gap that may be measured rather than treating planning as one undifferentiated score. It does not establish that task-specific VLM training, curriculum learning, rendered observations, or typed certificates will close that gap. The cited work neither trains a VLM nor uses the proposed per-step Planning Certificate. Any claim that this project improves structural search requires its own controlled evidence.

## 3. Independent assessment of the current repository and written proposal

### Established repository evidence

The current checkout is a StarVLA fork with a planning research layer. The following local materials define the present written scope and the evidence-bearing components. The GitHub links point to the `manuscript` branch for supervisor inspection.

| Local path | Role in the current work | GitHub link |
| --- | --- | --- |
| `docs/research_proposal.md` | Research proposal | [Source](https://github.com/Sino-Huang/multimodality_on_planning/blob/manuscript/docs/research_proposal.md) |
| `docs/high_level_plans/research_implementation_spec.md` | Current method specification | [Source](https://github.com/Sino-Huang/multimodality_on_planning/blob/manuscript/docs/high_level_plans/research_implementation_spec.md) |
| `docs/high_level_plans/research_execution_plan.md` | Execution plan and gates | [Source](https://github.com/Sino-Huang/multimodality_on_planning/blob/manuscript/docs/high_level_plans/research_execution_plan.md) |
| `CONTEXT.md` | Project-wide canonical terminology | [Source](https://github.com/Sino-Huang/multimodality_on_planning/blob/manuscript/CONTEXT.md) |
| `scripts/phase3/cgas_certificate_contracts.py` | Typed certificate contracts | [Source](https://github.com/Sino-Huang/multimodality_on_planning/blob/manuscript/scripts/phase3/cgas_certificate_contracts.py) |
| `scripts/phase3/cgas_certificates.py` | Certificate generation and deterministic checking | [Source](https://github.com/Sino-Huang/multimodality_on_planning/blob/manuscript/scripts/phase3/cgas_certificates.py) |
| `scripts/phase3/cgas_planimation_evidence.py` | Planimation evidence and certification support | [Source](https://github.com/Sino-Huang/multimodality_on_planning/blob/manuscript/scripts/phase3/cgas_planimation_evidence.py) |
| `scripts/phase3/cgas_trace_contract_v3.py` | Compact trace contract | [Source](https://github.com/Sino-Huang/multimodality_on_planning/blob/manuscript/scripts/phase3/cgas_trace_contract_v3.py) |
| `scripts/phase3/cgas_pilot_planimation_adapter.py` | Pilot data and Planimation adapter | [Source](https://github.com/Sino-Huang/multimodality_on_planning/blob/manuscript/scripts/phase3/cgas_pilot_planimation_adapter.py) |
| `scripts/phase3/cgas_qwenvl.py` | Current QwenVL-related project support | [Source](https://github.com/Sino-Huang/multimodality_on_planning/blob/manuscript/scripts/phase3/cgas_qwenvl.py) |
| `outputs/image_frames/` | Rendered image-frame outputs | [Source](https://github.com/Sino-Huang/multimodality_on_planning/tree/manuscript/outputs/image_frames) |
| `manuscript/CONTEXT.md` | Manuscript-local canonical terminology and claim boundaries | [Source](https://github.com/Sino-Huang/multimodality_on_planning/blob/manuscript/manuscript/CONTEXT.md) |

The audit records the following as implemented or evidenced.

* There are 23 Planimation domains or assets.
* A 15-domain curriculum PDDL generator accepted 3,600 instances.
* Typed BFS and IW Planning Certificate contracts and a deterministic verifier exist.
* The repository contains a one-invariant counterfactual generator and a compact trace contract.
* There are 411 accepted supervised examples, split into 363 training, 28 development, and 20 test examples.
* Certified 4-, 8-, and 12-object localhost smoke Attempts passed all eight Integration Certification claims under the pinned backend. The evidence reports `hosted_requests=0`.

These are infrastructure, data, and verification findings. They establish that plans, rendered observations, certificates, and checks can be produced and retained within the audited scope. They do not establish that a learned model uses this material effectively.

### Current proposal assumptions and absent evidence

The audit records no `planning_vlm/` package, trained planning model, supervised fine-tuning run, GPU run, checkpoint, Gate-3 run, Live Memory implementation, Route Label generator, adaptive controller, or comparative CGAS efficacy result. There is therefore no result showing that training improves a Verified Joint Step, a rollout, or structural search behavior.

The issue tracker shows that the planned work remains gated. The available issue index is grouped below. Each number is linked so the current scope can be checked directly.

| Group | GitHub issues | Current relevance |
| --- | --- | --- |
| Master specification | [#1](https://github.com/Sino-Huang/multimodality_on_planning/issues/1) | Master specification |
| Closed certification milestones | [#2](https://github.com/Sino-Huang/multimodality_on_planning/issues/2), [#3](https://github.com/Sino-Huang/multimodality_on_planning/issues/3), [#4](https://github.com/Sino-Huang/multimodality_on_planning/issues/4), [#5](https://github.com/Sino-Huang/multimodality_on_planning/issues/5), [#6](https://github.com/Sino-Huang/multimodality_on_planning/issues/6), [#7](https://github.com/Sino-Huang/multimodality_on_planning/issues/7) | Closed certification milestones |
| Plan sourcing and no-hosted revision | [#8](https://github.com/Sino-Huang/multimodality_on_planning/issues/8) | Scope revision. The ADR referenced by this issue is missing. |
| Pilot, calibration, routing, and final evaluation | [#9](https://github.com/Sino-Huang/multimodality_on_planning/issues/9), [#10](https://github.com/Sino-Huang/multimodality_on_planning/issues/10), [#11](https://github.com/Sino-Huang/multimodality_on_planning/issues/11), [#12](https://github.com/Sino-Huang/multimodality_on_planning/issues/12), [#13](https://github.com/Sino-Huang/multimodality_on_planning/issues/13), [#14](https://github.com/Sino-Huang/multimodality_on_planning/issues/14), [#15](https://github.com/Sino-Huang/multimodality_on_planning/issues/15), [#16](https://github.com/Sino-Huang/multimodality_on_planning/issues/16), [#17](https://github.com/Sino-Huang/multimodality_on_planning/issues/17), [#18](https://github.com/Sino-Huang/multimodality_on_planning/issues/18), [#19](https://github.com/Sino-Huang/multimodality_on_planning/issues/19), [#20](https://github.com/Sino-Huang/multimodality_on_planning/issues/20), [#21](https://github.com/Sino-Huang/multimodality_on_planning/issues/21) | Pilot corpus, Gate-3 training and evaluation, Live Memory, Route Labels, routing, test freeze, and five-seed evaluation |
| Backbone and generalization | [#22](https://github.com/Sino-Huang/multimodality_on_planning/issues/22), [#23](https://github.com/Sino-Huang/multimodality_on_planning/issues/23), [#24](https://github.com/Sino-Huang/multimodality_on_planning/issues/24), [#25](https://github.com/Sino-Huang/multimodality_on_planning/issues/25), [#26](https://github.com/Sino-Huang/multimodality_on_planning/issues/26), [#27](https://github.com/Sino-Huang/multimodality_on_planning/issues/27), [#28](https://github.com/Sino-Huang/multimodality_on_planning/issues/28), [#29](https://github.com/Sino-Huang/multimodality_on_planning/issues/29) | Backbone and generalization work |
| FF and Graphplan transfer | [#30](https://github.com/Sino-Huang/multimodality_on_planning/issues/30), [#31](https://github.com/Sino-Huang/multimodality_on_planning/issues/31), [#32](https://github.com/Sino-Huang/multimodality_on_planning/issues/32), [#33](https://github.com/Sino-Huang/multimodality_on_planning/issues/33), [#34](https://github.com/Sino-Huang/multimodality_on_planning/issues/34), [#35](https://github.com/Sino-Huang/multimodality_on_planning/issues/35), [#36](https://github.com/Sino-Huang/multimodality_on_planning/issues/36), [#37](https://github.com/Sino-Huang/multimodality_on_planning/issues/37) | Planned FF and Graphplan transfer |

The full project suite has 13 documented pre-existing collection errors. Together with the missing ADR from issue #8, these are evidence limitations that should remain visible in any supervisor discussion. They are not grounds for inventing completed model results or treating the plan as executed.

## 4. What the current CGAS proposal actually means

### Current written specification

The current CGAS design uses symbolic BFS or IW offline. Those algorithms produce replayable action and Planning Certificate traces. At each replayed transition, a VLM receives the current rendered observation, task or goal, and planner-family identifier. It predicts one grounded action and one typed Planning Certificate.

The training rows are plan transitions, not search expansions. The primary defined outcome is a **Verified Joint Step**, where the action is applicable, the Planning Certificate satisfies its invariants, and the action and certificate describe the same transition. Whole-plan rollout is a secondary measure.

The written design also defines Adaptive Scaffolding through three Support Routes selected before prediction. The direct route provides the current information boundary. The certificate route adds the immediately preceding verifier-approved Planning Certificate. The memory route adds earlier verifier-approved records that are local to the problem instance. Route Labels are defined through counterfactual execution of the same frozen model and identify the least-cost Support Route that produces a Verified Joint Step.

This is action-and-certificate stepwise policy learning with Adaptive Scaffolding. It is not model-owned neural search. The written design does not specify a model-owned frontier, closed set, novelty state, node expansion mechanism, selection among search candidates, or complete-plan generation procedure.

## 5. My main concern about the current proposal

### My concern

BFS and IW may serve as expert teachers or reference algorithms, but a trace generated by either algorithm has already resolved the structural search choice. A model trained only on those replayed transitions may learn local trace imitation. It may predict a legal next action and a locally valid Planning Certificate without learning when a different branch should be explored, when a state is a dead end, or how a long-horizon search state should change.

If a deterministic manager chooses the frontier, node, ordering, and search state, that manager performs the search. In that arrangement, the VLM is a successor or action proposer. Calling the outcome model-guided search would require evidence that a model decision changes the exploration order or the resulting plan under a stated budget.

Planning Certificates also need a defined causal role. If a manager recomputes all transition and search invariants, a certificate can become decorative or redundant. A useful certificate should describe a model-proposed action or search update that the trusted checker validates. The checker can reject an invalid certificate, but it should not silently supply the decision or use the teacher trace to repair it.

### Independent assessment

BFS and IW are not automatically upper bounds on every learned search policy. Their optimality or resource behavior depends on the task objective, symbolic representation, pruning policy, and search budget. A learned method might use a different ordering or heuristic and reach a goal with fewer expansions under a fixed budget. Conversely, matching a teacher trace does not prove that the model can search without the trace. BFS and IW should be treated as reference behavior and label generators. The evaluation should distinguish imitation of an expert policy from general search competence.

## 6. The verifier concern and the scope boundary

### My concern

A task- and domain-specific deterministic verifier is valuable as an experimental measurement instrument for formalized planning. It can check action applicability, state progression, Planning Certificate invariants, and agreement between an action and its claimed transition. This makes a Verified Joint Step a clear and reproducible outcome.

The same verifier is not a universal verifier for arbitrary natural-language tasks. It does not resolve ambiguous goals, incomplete world knowledge, or disagreements about the intended semantics of an open-world instruction. The honest initial scope is therefore formal PDDL and renderer domains with fixed transition semantics. Later work could study semantic parsing into a fixed formal interface or compare against independently maintained simulators. Those extensions would need separate measures for language grounding and interface errors.

Allowing the evaluated agent to author the verifier that judges its own predictions creates circularity. The model and its generated verifier could share the same mistaken rule and still report acceptance. The trusted domain contract, checker, and test instances should be fixed independently of the evaluated model before testing. This boundary makes the work a controlled scientific study. It does not make a claim to solve open-world natural-language planning.

## 7. My current research assessment

### Independent assessment and proposed redesign

The existing verifier-based CGAS materials should be treated as an infrastructure, data, and evaluation foundation. Stepwise CGAS can remain a useful baseline for local operational behavior. The central target should be revised toward curriculum- and modality-conditioned learning of structural search if that remains the intended contribution.

One concrete formulation is externally managed, model-guided search. The VLM must make an observable search decision. Depending on the condition, it can select or rank an expansion candidate, identify a landmark or subgoal, propose a search-state update, or choose a branch. It must also emit a typed Planning Certificate describing the selected action or update. A deterministic checker validates the prediction and records whether it is accepted.

A manager may store canonical frontier, closed-state, and novelty information, apply trusted transitions, and reconstruct a final plan. Those roles maintain a fixed and inspectable state representation. The manager must not silently choose the model's expansion, rank candidates with an undisclosed heuristic that determines the decision, or replace rejected model decisions. Each such intervention would make the manager the effective search policy. Rejected predictions must have a declared cost or failure outcome.

An internal model-owned search design is the alternative. In that design, the model maintains its own frontier, closed set, novelty state, and backtracking information. This is closer to the strongest interpretation of “learn to search.” It is also riskier because it combines state retention, structural reasoning, action grounding, and output serialization in one measurement. It is less aligned with the existing deterministic infrastructure and makes error attribution harder. The externally managed formulation is the more direct next target if the aim is to isolate model-guided search decisions.

## 8. Concrete curriculum and evaluation design

### Proposed redesign

The curriculum should independently vary an operational axis and a structural axis. The operational axis should contain action applicability, state progression, Planning Certificate correctness, and action-certificate agreement. The structural axis should contain landmark identification, reachability, branch or expansion selection, search-state updates, and budget-aware exploration. Independent variation prevents a structural result from being explained only by easier local transitions.

The core modality comparison should use matched text-only, rendered-visual, and multimodal controls. Each condition should see the same symbolic task content at the intended information boundary. Compare action-only training against Joint Action-and-Certificate SFT. Difficulty can vary landmarks, horizon, branching, object count, composition, naming, and render corruption. Test sets should include held-out structural shifts, such as changed branching regimes or unfamiliar landmark dependencies. Cross-algorithm transfer from BFS or IW to FF or Graphplan conditions is useful if the planned transfer work becomes feasible.

The outcome set should include per-axis competence, landmark and reachability accuracy, valid search-update rate, Planning Certificate fidelity, legal-goal and verified rollout success, expansion count or search cost, and a prespecified failure taxonomy. The taxonomy should distinguish invalid actions, invalid certificates, action-certificate mismatch, incorrect search-state updates, poor expansion choices, budget exhaustion, and goal-recognition errors. Raw PDDL success or exact teacher-trace match alone cannot identify whether the model learned local prediction or structural search.

Required controls are a manager-only condition, a random proposer, a strong classical proposer, action-only and certificate-removal conditions, matched modality ablations, and no-oracle-leakage checks. The manager-only control establishes what trusted symbolic machinery can achieve without learned decisions. The random and classical proposers locate the task relative to chance and available algorithmic references. The action-only and certificate-removal controls test whether typed Planning Certificates add measured value. No-oracle-leakage checks must prevent test-time access to teacher traces, hidden planner ordering, future states, or a manager decision that chooses the expansion for the model.

This design directly handles the teacher and upper-bound issue. BFS and IW can provide valid targets for initial supervision and a strong reference. Evaluation must also contain settings with multiple valid action orders, changed names or renderings, and held-out structural conditions. Score accepted updates and search outcomes under the same budget, rather than token-level agreement with a single teacher trace.

## 9. How to use the current CGAS artifacts

### Independent assessment

The following artifacts should be retained because they are useful for the revised target.

* Typed Planning Certificate contracts and deterministic invariants can define checkable action and search-update targets.
* The one-invariant counterfactual generator can create controlled local violations and may support diagnostic labels.
* Trace, replay, and provenance material can support reproducible training rows and evaluation records.
* Planimation Integration Certification and the existing 4-, 8-, and 12-object smoke Attempts should remain infrastructure validation for rendering, Plan Submission, Plan Interpretation, Plan Provenance, Render Production, and Render Validation.
* Evidence Bundles should retain the records needed for independent checking of an Attempt.

The smoke Attempts do not demonstrate model training or improved search. Adaptive Scaffolding, Support Routes, Live Memory, and Route Labels should be demoted from the headline unless an experiment shows that they answer the revised structural-search question. They can remain optional ablations or later mechanisms. The central claim should not depend on their implementation until evidence exists.

## 10. Provisional research statement

### Unapproved and contingent on supervisor review

**Central question.** Under fixed formal planning semantics and a trusted deterministic manager, can curriculum- and modality-conditioned Joint Action-and-Certificate SFT improve a VLM's observable structural search decisions separately from its local operational competence, and when do rendered observations help, hurt, or make no measured difference relative to text-only input?

**Provisional contribution claim.** The proposed study would provide a controlled evaluation in which a VLM makes verifier-checkable search decisions under text-only, rendered-visual, and multimodal curricula. It would separate local action-and-certificate behavior from structural search behavior with matched manager and classical controls. This is an unapproved proposal and does not claim a result.

The key threat is “classical search did all the work.” Evidence needed to answer that threat includes a declared model decision interface, manager-only and fixed-policy controls, accounting for rejected predictions, search-update measures, and plan or expansion outcomes that differ because of the model decision under the same manager and budget.

## 11. Recommended decision sequence

### Proposed process before implementation changes

1. The supervisor first chooses the scientific target. The decision is between stepwise policy learning and model-guided structural search.
2. Define the model's search output and the trusted manager boundary. State exactly which decision belongs to the model, which state the manager may store, and how rejections affect the budget.
3. Define the curriculum and modality factors, the operational and structural labels, the held-out shifts, and the required controls.
4. Revise the proposal, implementation specification, execution plan, and issue tracker to match the approved target and evidence boundary.
5. Implement training and evaluation only after that review and revision are complete.

No existing research document should be changed until the supervisor review resolves the scientific target and the model-manager boundary. The current repository supports infrastructure and data claims. It does not yet support training, comparative efficacy, or improved-search claims.
