# Partial Obsolescence Exceptions

**Status:** resolved for the active code path
**Decision source:** GitHub issue #38, “Spec: Teach VLMs executable search processes across modalities”

The issue-38 Search Process Policy program is the active research target. The
former CGAS target remains historical context only and is not an efficacy
claim for the current study.

The migration retained the reusable scientific behavior:

- local BFS, IW, FF-style, Graphplan, and PDDL replay semantics;
- typed traversal events and concrete-state projection;
- Planimation supplied-plan rendering and semantic image validation;
- normalized action-sequence provenance under the pinned backend revision;
- whole-instance splits, deterministic generation, and rollout coverage gates.

The migration removed the temporary integrity, publication, receipt-chain,
pilot-index, representative-mapping, certificate-publication, and output-layout
layers that previously surrounded those behaviors. Current persisted records
use paths, readable semantic identities, ordered records, and direct replay
comparisons.

Historical research documents under `docs/detailed_implementation_summary/`
may still describe the demoted experiments. They are narrative history, not
live interfaces or current evidence. `research_target_assessment.md` remains
the canonical historical disposition record and must not be presented as an
issue-38 result.

The preferred current seam is the `Search Episode Harness` in
`examples/planning_benchmark_slice`: formal task, declared algorithm, modality
adapter, policy adapter, and frozen budget enter; a complete replayable episode
and semantic evidence record leave.
