# Supervisor Brief on the Planning and Multimodality Study

> **Historical status notice (2026-08-31).** This brief records the pre-Search-Process-Policy decision context from 2026-08-17. It is retained to explain why the program moved beyond CGAS, but its repository-status statements are superseded by `manuscript/content_brief.md`, `manuscript/writing_design_tree.md`, and GitHub issues #54--#111. In particular, issue #54 now retains trained BFS process-SFT checkpoints and a governed v8 development-panel `VALID_STOP`; issues #55--#58 establish the BFWS successor path, exact traces, and released text corpus. Statements below that no trained model or structural-search infrastructure exists must not be used as current evidence.

## 1. Purpose and executive summary

This brief separates the present evidence base from the current CGAS specification and from the intended VLM research question. **Established repository facts** describe an audited checkout on 2026-08-17. **Current proposal assumptions** describe the written CGAS design and are not training results. **Author concern** records the question of whether the study would test learned search or mainly local action prediction under symbolic support. **Proposed alternatives** are options for supervisor review, not approved commitments.

The repository has a substantial planning-data and verification foundation, but it has no trained planning VLM or model-side search system. The current proposal trains a VLM on replayed transitions to predict one grounded action and one typed Planning Certificate, then evaluates a Verified Joint Step as the main outcome. That is a defensible operational-reasoning study. It does not yet test whether a model can choose and manage structural search. The recommended direction is to retain stepwise CGAS as a diagnostic baseline while defining a separate, externally managed but model-guided search condition. A deterministic manager may hold canonical state and check transitions, while the model must make the choices that determine which node or candidate is explored. The evaluation should then separate operational from structural behavior and test when rendered observations add information, add noise, or make no difference.

## 2. What exists now and what is only proposed

**Established repository facts.** The audit describes this checkout as a StarVLA fork with a planning research layer. It records implemented or evidenced planning assets, data generation, symbolic contracts, and localhost rendering checks. It records no trained model or the model-learning components needed for the proposal.

| Area | Status on 2026-08-17 | Evidence-bearing statement |
| --- | --- | --- |
| Planimation material | Implemented or evidenced | The checkout contains 23 Planimation domains or assets. |
| Curriculum instances | Implemented or evidenced | A 15-domain curriculum PDDL generator accepted 3,600 instances. |
| Symbolic contracts | Implemented or evidenced | Typed BFS and IW Planning Certificate contracts, a deterministic verifier, a one-invariant counterfactual generator, and a compact trace contract are present. |
| Supervised corpus | Implemented or evidenced | There are 411 accepted examples, split into 363 train, 28 development, and 20 test examples. |
| Rendering checks | Implemented or evidenced | Certified 4-, 8-, and 12-object localhost Planimation smokes passed all eight Integration Certification claims under the pinned backend, with `hosted_requests=0`. |
| VLM implementation and training | Not implemented or evidenced | There is no `planning_vlm/` package, trained model, SFT run, GPU run, checkpoint, or Gate-3 calibration. |
| Adaptive components | Not implemented or evidenced | There is no Live Memory module, Route Label generator, adaptive controller, or comparative CGAS result. |
| Remaining gates | Open | GitHub issues from #8 onward gate the pilot corpus, Gate-3 training and evaluation, Live Memory, route labels, routing, final-test freeze, five-seed evaluation, and FF or Graphplan transfer. |

**Established repository facts.** Issue #8 records a plan-sourcing and no-hosted scope revision, but the ADR it references is absent. The documented full project suite also has 13 pre-existing collection errors. These observations limit the claims that can be made from the current audit. They do not justify filling evidence gaps with invented results.

**Current proposal assumptions.** The written CGAS specification uses a current rendered observation, goal or task, and planner-family identifier as VLM input. The intended output is one grounded action and one typed Planning Certificate. Training replays transitions from symbolic BFS or IW traces. It does not supervise search expansions. Verified Joint Step is the primary metric, with whole-plan rollout secondary.

**Current proposal assumptions.** BFS and IW run symbolic search offline and supply action and certificate traces. The direct, certificate, and memory Support Routes are specified, along with a pre-prediction route controller. The certificate route provides the immediately preceding verifier-approved certificate. The memory route provides earlier verifier-approved records local to the instance. The specification does not define neural node expansion, model-owned frontier, closed set, or novelty state, model selection among search candidates, or complete-plan generation. It also avoids claims about in-context learning, Experience Distillation, and off-plan action supervision.

## 3. The mismatch with the intended research question

**Author concern.** The intended project is a VLM training study about curriculum learning across modalities and its effect on planning behavior. The author wants to ask whether training can improve structural abilities such as identifying landmarks, choosing a path to explore, tracking frontier or search-state status, and judging reachability. The same study should establish when visual observations help, hurt, or add no useful information.

**Current proposal assumptions.** Stepwise CGAS instead asks whether a model can predict the next action and a verifier-checkable certificate from a replayed transition. This can test local applicability, progression, and certificate consistency. A rollout assembled from such predictions can fail for reasons that are invisible at a single step, but successful local predictions do not by themselves demonstrate model-guided enumeration or search control.

The distinction matters because a model can concatenate locally plausible actions while relying on a teacher trace that already resolved the structural choice. The current direct, certificate, and memory routes may be valuable ablations of information boundaries. They are not yet an experiment in which the model owns an expansion decision. Stepwise CGAS should therefore be framed as an operational baseline and a measurement component for a larger search study, unless the research question is intentionally narrowed to verifiable next-step prediction.

## 4. BFS and IW as teachers and as reference behavior

**Established repository facts.** The available BFS and IW contracts, verifier, and trace generation make these planners useful sources of grounded action and Planning Certificate targets. They provide deterministic reference behavior for the represented domains, expose state transitions that can be checked, and support counterfactual examples under the existing one-invariant generator.

**Author concern.** A classical planner is a teacher or oracle for a particular representation and search policy. Treating its trace as the only correct behavior can turn training into trace imitation. It can also obscure whether the model learned a general search heuristic, learned an incidental ordering convention, or copied the teacher's local decisions.

BFS or IW is not automatically an upper bound on every learned policy. Search optimality is conditional on the planner, objective, representation, pruning rules, and resource budget. A learned policy may use a different ordering, representation, or learned heuristic and still reach a goal with fewer expansions under a defined budget. Conversely, imitation of an optimal teacher trace does not establish that the model can find a plan when the trace is absent. The comparison must distinguish quality of the teacher's search result from the model's ability to use or depart from that reference.

**Proposed alternatives.** Use teacher traces for initial action and certificate supervision, then include held-out tasks with multiple valid action orders, changed predicate or object naming, altered renderings, and structural shifts. Score state transitions and search decisions rather than exact teacher-token agreement. Where feasible, give a model access to a manager-maintained candidate set and evaluate its ranking or selection against a fixed expansion budget. Compare against the teacher and against a manager-only planner. These choices make copying a particular trace insufficient for a strong result.

## 5. The verifier concern and honest scope

**Author concern.** A supplied deterministic verifier at test time can make a planning result look less applicable to open natural-language tasks. That concern is valid if the result is described as a general solution to unconstrained language planning.

A task- and domain-specific deterministic verifier is valid as a measurement instrument. It can establish whether a grounded action is applicable, whether the successor state follows the declared transition rules, and whether a Planning Certificate matches that transition. This supports the defined metric of a Verified Joint Step. It does not provide a universal semantic checker for natural-language goals, ambiguous environment descriptions, or missing world knowledge.

Letting an agent author the verifier that grades its own predictions creates circularity. The evaluator may then accept errors shared by the agent and its generated rules. The benchmark should hold the domain model, verification code, and test instances fixed before evaluation. Any learned verifier should be a separate study with independently labeled checks and an evaluator that is not authored or modified by the evaluated agent.

**Proposed alternatives.** Scope the first study to formalized planning domains with known symbolic transition semantics and rendered observations. Report verifier access as part of the task definition, not as an implicit capability of the model. A later generalization study could examine semantic parsing from natural language into a fixed formal interface, uncertainty-aware verification, or independently maintained simulators. Those studies should separately measure parsing and grounding errors before making claims about open-ended planning.

## 6. The cited paper and its contribution

**Established external reference.** Sukai Huang et al., *What We Talk About When We Talk About LLM Planning: Evidence for Two Distinct Planning Abilities* (arXiv:2607.11197, 2026) evaluates open-weight text LLMs without task-specific training on ACPBench-Hard. The benchmark has 1,040 items across eight subtasks. These include applicability, progression, and validation alongside reachability, landmark, and areachability tasks. It evaluates direct, chain-of-thought, and scratchpad conditions with a symbolic PDDL validator and multidimensional item-response theory.

The paper reports that a two-dimensional noncompensatory account fits best, separating operational reasoning from structural enumeration. Scaling and chain-of-thought improve operational reasoning in the reported analysis, while structural enumeration remains relatively flat. Scratchpad traversal does not remove the reported structural bottleneck. Output format also has a large effect on apparent structural performance.

**Why this supports the motivation.** The result gives a concrete reason to measure local transition competence separately from structural search competence. It is compatible with the author's expectation that present language or vision-language models may handle immediate precondition checks and progression more readily than reachability, landmark identification, or search-state management.

**What remains open.** The cited study does not train a VLM, does not test curriculum learning across modalities, and does not use a per-step typed invariant certificate. It is a companion motivation. It does not prove that task-specific multimodal training will improve structural enumeration, nor does it establish that certificates or rendering will solve the reported bottleneck.

## 7. Revised research idea

**Proposed alternative.** Study curriculum- and modality-conditioned learning of verifiable structural search in formal planning domains. The central question is whether training can improve a model's search decisions while an external deterministic manager maintains the canonical symbolic state and checks the consequences of those decisions. The manager is a measurement and execution boundary. The model is the source of the search policy under test.

In one externally managed condition, the manager stores frontier entries, closed-state status, novelty data where applicable, state identifiers, and verified successors. It exposes a bounded representation of the available search decision. The model chooses an expansion target, ranks candidates, proposes an action, or makes another decision that changes exploration under a declared interface. The manager validates the action and Planning Certificate, applies the transition, and records the outcome. A rejected prediction must count toward a defined error or budget rule.

The model contribution must be isolated. If the manager chooses which node to expand, ranks candidates, applies a fixed heuristic that determines ordering, or silently replaces failed model proposals, the procedure is not model-guided search. It is a classical search system with a model attached. Manager-only and fixed-policy controls are necessary to quantify what the model decision changes.

**Alternative with higher ambition.** An internal model-owned search condition would require the model to represent frontier, closed-set, novelty, and backtracking state itself. This aligns most closely with the phrase “learn to search,” but it confounds search-state retention with action grounding and makes verification harder. It should be treated as a later condition unless the project can define an observable search-state interface and evaluate it directly.

## 8. Curriculum and evaluation sketch

**Proposed alternative.** Build curricula on two separately labeled axes. The operational axis covers action applicability, state progression, certificate correctness, and action-certificate agreement. The structural axis covers reachability, landmark identification, expansion choice, search-state updates, and resource-aware exploration. Vary the axes independently where possible so a result cannot be explained by easier local transitions alone.

Use matched text-only, rendered-visual, and multimodal conditions. Compare action-only training with Joint Action-and-Certificate SFT. The curriculum can vary landmarks, horizon, branching, object count, compositional structure, naming conventions, and render corruption. Held-out evaluation should include structural shifts rather than only new instances sampled from the training generator.

The scorecard should include per-axis correctness, reachability and landmark accuracy, valid search-update rate, verified rollout and goal success, expansion efficiency, and a prespecified failure taxonomy. Raw PDDL success alone cannot identify whether a method improved local transition prediction, search selection, or exploitation of the manager. The failure taxonomy can distinguish invalid action, invalid certificate, action-certificate mismatch, stale search-state update, poor expansion choice, budget exhaustion, and goal-recognition error.

Controls should include a manager-only baseline, random and classical proposers, and certificate-removal conditions. The manager-only result identifies what the deterministic system can achieve without a learned decision. Classical proposer results locate the task relative to the available symbolic references. Certificate removal tests whether any effect comes from the typed Planning Certificate rather than from added tokens alone. Run five seeds and use instance-level paired bootstrap intervals only if compute and the final test freeze make those procedures feasible. If they are not feasible, state that limitation and avoid seed-stability claims.

## 9. Design choices for supervisor discussion

| Option | What it tests | Recommendation | Likely reviewer objection | Evidence needed |
| --- | --- | --- | --- | --- |
| Current stepwise CGAS | Local grounded action and Planning Certificate prediction under direct, certificate, or memory Support Routes | Keep as a baseline and diagnostic | “This is next-step imitation, not planning or search.” | Verified Joint Step results, rollouts, route ablations, and careful bounded claims. |
| External verified model-guided search | Model expansion or candidate decisions with deterministic state storage and checking | Recommended next research design | “The manager, not the model, performs the planning.” | A declared model decision interface, manager-only and fixed-policy controls, search-update metrics, and expansion-efficiency gains beyond controls. |
| Internal model-owned search | Model maintains and updates its own search state | Defer unless a clear observable interface is feasible | “State errors and grounding errors are confounded, and the system is not reproducible.” | Direct search-state labels, update checks, failure attribution, and controlled comparisons to the external-manager condition. |

The recommended path makes a narrower claim than full internal search while directly addressing the structural-enumeration question. It also preserves the existing evidence base. An ICLR reviewer may object that visual input is decorative, that teacher supervision causes trace copying, that verifier access hides the problem, that the task is too narrow, or that stochastic training effects are underpowered. Matched modality controls, multi-solution and held-out structural tests, explicit verifier scope, transfer across formal domains, a final frozen test set, and five-seed analysis where feasible provide corresponding evidence. They do not remove every limitation, but they make the limits visible and testable.

## 10. Proposed research question and contribution claim

**Proposed research question.** Under fixed formal planning semantics and deterministic verification, can curriculum and modality-conditioned Joint Action-and-Certificate SFT improve a VLM's operational and structural search decisions, and under which task conditions do rendered observations improve, degrade, or leave unchanged those decisions relative to text-only input?

**Provisional contribution claim, not yet approved.** The proposed study would introduce a controlled evaluation of curriculum- and modality-conditioned VLM planning that separates verifier-checkable local transition competence from model-guided structural search decisions. It would compare text-only, rendered-visual, and multimodal input under explicit manager and verifier boundaries. This is a proposed contribution. No current repository evidence establishes that the training method improves any outcome.

## 11. Immediate next steps before changing research documents

1. Decide whether the primary claim is stepwise verified prediction, external verified model-guided search, or internal model-owned search. Record the decision and the allowed role of any deterministic manager.
2. Recover or replace the missing ADR referenced by issue #8 so plan sourcing and the no-hosted boundary are explicit and reviewable.
3. Define a frozen task contract that states the model input, manager-visible state, model decision, verifier access, budget accounting, and failure handling for each condition.
4. Specify the operational and structural label sets, the matched modality controls, and the held-out structural shifts before corpus expansion or training.
5. Write the baseline matrix and analysis plan, including manager-only, random or classical proposer, certificate-removal, seed, and paired-bootstrap conditions. Mark any unavailable compute or test-freeze prerequisite as a limitation.
6. Resolve or clearly isolate the 13 documented pre-existing collection errors before treating suite-level results as final evidence.
7. Only after these choices are approved, revise the proposal and research documents to match the decided scientific claim. The current audit supports infrastructure and data statements. It does not support training or comparative performance statements.
