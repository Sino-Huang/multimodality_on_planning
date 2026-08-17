# Partial Obsolescence Exceptions

**Status:** active exception register
**Scope:** CGAS to Search Process Policy realignment
**Decision source:** GitHub issue #38, `Spec: Teach VLMs executable search processes across modalities`

This register records files that mix retained infrastructure with the demoted
CGAS research target. They stay in place until the new specification is
accepted and the affected modules or documents are deliberately rewritten.
Moving a file listed here would either remove reusable evidence, break a
retained import seam, or destroy the canonical history needed for migration.

The register is not an implementation exception that changes runtime behavior.
It is a documentation and maintenance exception: each entry remains usable for
its retained purpose, while the obsolete portion must not be used as evidence
for the new research claim.

## Exception Rules

1. Keep every listed file at its current path until its replacement contract is
   approved and its callers/tests are migrated.
2. Treat only the retained portions described below as current evidence.
3. Treat CGAS headline claims, Support Routes, Live Memory, Route Labels,
   Planning Certificates as the primary model target, and CGAS efficacy claims
   as stale for the new study.
4. Do not silently rename current canonical terms in `CONTEXT.md`; revise that
   glossary only through the approved documentation migration.
5. Resolve an exception by either splitting the retained Module from the old
   policy-specific implementation or rewriting the document section, followed
   by the relevant contract and integration tests.

## Documentation Exceptions

### Root and high-level documents

- `docs/research_proposal.md`: retain the motivation, typed BFS/IW evidence,
  verifier invariants, modality-parity intent, and instance-level statistics;
  revise its scaffold palette, counterfactual scaffold, external-memory,
  CGAS-calibration, Support Route, Live Memory, Route Label, Pareto, and CGAS
  efficacy sections after issue #38 approval.
- `docs/high_level_plans/research_execution_plan.md`: retain gate ordering,
  falsification, no-oracle-leakage, instance-level uncertainty, Integration
  Certification, BFS control, and IW material; revise CGAS routing, memory,
  calibration-as-go/no-go, and CGAS headline sections.
- `docs/high_level_plans/research_implementation_spec.md`: retain the
  Integration Certification contract, verifier contracts, split protocol, and
  statistical/cost-order material; revise Support Routes, Live Memory, Route
  Labels, the CGAS Pareto rule, and CGAS-specific scope boundaries.
- `CONTEXT.md`: Plan Submission, Plan Interpretation, Action Sequence, Render
  Production, Render Validation, Plan Provenance, Integration Certification,
  Attempt, and Evidence Bundle remain current. Adaptive Scaffolding, Support
  Route, Live Memory, Route Label, Joint Action-and-Certificate SFT, Planning
  Certificate as the headline target, and Verified Joint Step as the headline
  outcome require later terminology review.
- `task_plan.md`: retain active rendering, replay alignment, and Planimation
  smoke operations; revise CGAS calibration-corpus framing.
- `notes.md`: retain rendering and pilot facts; revise stale CGAS framing.
- `phase3_pilot_materialization_closeout.md`: retain pilot-rendering evidence;
  revise its CGAS corpus interpretation.

### Detailed implementation summaries

The 56 files remaining in `docs/detailed_implementation_summary/` after the
fully obsolete 29-file characterization/partition/publication set is moved
are partial exceptions. Their retained material falls into these groups:

- Integration Certification, Planimation rendering, verifier, provenance, and
  state/frame pairing evidence.
- Search, traversal, curriculum, local planner, expert-trajectory, and VLM
  conversion material reusable for canonical search-process traces.
- Certificate, alignment, and counterfactual mechanisms retained as diagnostic
  or verification infrastructure, not as the headline method.
- Code-health, refactor, concurrency, output-layout, and execution-governance
  records that remain repository maintenance evidence.

Their obsolete portions are historical CGAS phase framing, certificate-led
training interpretation, pilot-corpus claims, or CGAS-specific execution
goals. Each summary must be revised or split after the new master contract is
approved; none is evidence that a trained Search Process Policy exists.

## Code Exceptions

### Retained Phase-3 Modules with mixed responsibilities

- `scripts/phase3/cgas_certificate_contracts.py`: retain algorithm-fidelity
  expansion/event checks and counterfactual verification; later separate
  certificate-schema validation from the retained search verifier.
- `scripts/phase3/cgas_certificates.py`: retain the counterfactual/verifier
  facade; later remove or isolate certificate build/verify paths.
- `scripts/phase3/cgas_candidate_space.py`: retain `Candidate` and
  `build_candidate` while the Planimation adapter depends on them; later
  remove CGAS composition machinery after the adapter is refactored.
- `scripts/phase3/cgas_candidate_accounting.py`: retain the planner-input
  records required by the active adapter; later separate generic task
  accounting from CGAS accounting.
- `scripts/phase3/cgas_candidate_graph.py`: retain canonical graph identity
  used by candidate generation and accounting; later move the generic graph
  identity logic behind the approved task/observation Module.
- `scripts/phase3/cgas_characterization_rows.py` and
  `scripts/phase3/cgas_partition_contracts.py`: retain the composition
  signature and source contract required transitively by active candidate
  generation; later extract that generic signature from characterization and
  partition policy.
- `scripts/phase3/cgas_certificate_publication.py`: retain publication support
  required by the mixed certificate/counterfactual facade; later remove it
  when the obsolete certificate build path is split from retained diagnostics.
- `scripts/phase3/cgas_pilot_expansion_index.py`: retain state digest/index
  support used by rendering and replay alignment; later remove pilot-specific
  ownership after callers migrate.
- `scripts/phase3/cgas_pilot_representative_mapping.py`: retain provenance
  binding used by active rendering; later remove CGAS policy identifiers.
- `scripts/phase3/cgas_trace_contract_approval.py`: retain trace contract
  approval behavior; later rename/generalize policy-specific approval terms.
- `scripts/phase3/cgas_pilot_replay_alignment.py`: retain state/frame pairing;
  later split pilot binding from generic replay alignment.
- `scripts/phase3/cgas_pilot_render_coverage.py`: retain render coverage;
  later split pilot-specific coverage accounting.
- `scripts/phase3/cgas_pilot_planimation_adapter.py`: retain the dirty
  `StateRenderer` and supplied-plan rendering seam; later remove candidate,
  expansion, and representation-mapping bindings.
- `scripts/phase3/cgas_pilot_lama_first_renderer.py` and
  `scripts/phase3/cgas_pilot_planimation_production.py`: retain the dirty
  local-LAMA and authorized production paths; later separate generic
  rendering from CGAS pilot naming and scope.

These files are also protected from automated movement because several are
currently modified or untracked in the shared worktree.

### Remaining repository coupling

- `starVLA/dataloader/qwenvl_llavajson/qwen_data_config.py`: retain the base
  dataset registry; remove the `PLANNING_CGAS_V1_TRAIN` and
  `PLANNING_CGAS_V1_DEV` entries only after replacement registry entries are
  approved.
- `tests/planning_benchmark/test_dataset_registry.py`: retain the general
  registry tests; rewrite the test that hardcodes CGAS dataset paths to use
  the new planning benchmark smoke registry.
- `scripts/planimation_phase1_client.py`: retain the modified base rendering
  client; do not revert or move it.

### Legacy datasets with live references

- `data/planning_cgas_v1/`, `data/planning_cgas_fixture_v1/`, and
  `data/phase3_supervised_planning/`: these datasets are obsolete for the new
  headline, but the active dataset registry and planning-benchmark registry
  tests still reference part of the first dataset. Keep them until the
  registry is migrated and the replacement smoke data is verified.
- `outputs/cgas_readiness/`: generated readiness evidence is old CGAS output;
  it may be archived after callers and audit references are checked. It is not
  a current model result and must not be used as evidence for the new target.

## Preferred Test Seam

The new work should use the existing `examples/planning_benchmark_slice`
full-episode loop as the highest seam. Its Interface should become the deep
`Search Episode Harness`: a formal task, declared algorithm, modality
Observation Adapter, policy Adapter, and frozen budget enter; one complete
episode/evidence record leaves. Existing BFS/IW execution, trace verification,
PDDL progression, rollout gates, and Planimation pairing remain internal
Adapters behind that Interface. A*+h_max and A*+landmark-count become new
algorithm Adapters. Only deterministic trace invariants, modality parity,
no-policy-leakage, and snapshot sufficiency need narrower contract tests.

## Resolution Gate

No exception is resolved by this register. Resolution requires issue #38
acceptance, an approved terminology/runtime contract, migrated callers and
tests, and evidence that the retained behavior still passes its existing
Integration Certification and provenance checks.
