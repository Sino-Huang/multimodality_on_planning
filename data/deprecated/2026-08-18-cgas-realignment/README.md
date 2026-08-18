# CGAS Realignment Archive

**Archived:** 2026-08-18
**Replacement specification:** https://github.com/Sino-Huang/multimodality_on_planning/issues/38

This directory preserves files that were audited as wholly specific to the
demoted CGAS characterization, partition, production-publication, pilot-scope,
certificate-publication, or certificate-labelled QwenVL workflow. Their
original repository-relative paths are preserved below this directory.

The archive contains 144 moved paths:

- 29 detailed implementation-summary documents;
- fully CGAS-specific Phase-3 candidate, characterization, partition,
  production, release-gate, pilot-selection, QwenVL, and publication modules;
- the tests paired only with those deprecated modules; and
- three CGAS production/smoke configuration files.

**Supplemental archive (added later on 2026-08-18, not part of the initial
144-path count above):**

- `.claude/evidence/cgas-partition-characterization/`
- `.claude/evidence/production-p0-corpus-experiment-readiness/`
- `.claude/knowledge/vlm-adaptation-taxonomy-cgas-2026-08-16.md`

These three supplemental paths are historical CGAS material preserved under
this directory at their original repository-relative locations. They are not
current evidence for the Search Process Policy program (issue #38) and must
not be cited as such.

**Full cold-archive migration (later on 2026-08-18, not part of the counts
above):**

- `.claude/evidence/` — the full retired active evidence tree, moved wholesale
  and merged with the supplemental evidence roots above without overwriting:
  `cgas-phase3-pilot-manifest/`, `cgas-phase3-pilot-materialization/`,
  `cgas-phase3-pilot-rendering/`, `cgas-phase3-pilot-representative-mapping/`,
  `cgas-phase3-pilot-scope/`, `cgas-production-p0/`, `cgas-trace-contract-v3/`,
  `context-storage-slimming/`, `phase-a-planner-configuration-probe/`,
  `planimation-pilot-contract-and-render-recovery/`, and
  `task-4-cgas-dataloader-and-experiment-support/`;
- `.omo/` — the full retired tool-state tree (`knowledges/` and the empty
  `evidence/` directory);
- `tests/phase3/test_cgas_trace_contract_v3.py`,
  `tests/phase3/test_cgas_pilot_planimation_adapter.py`, and
  `tests/phase3/test_planimation_profile_regressions.py` — historical tests that
  directly consumed the archived evidence or were pilot-only, preserved at
  their original repository-relative locations. A fourth pilot test,
  `tests/phase3/test_cgas_pilot_planimation_production.py`, was untracked and
  user-owned at migration time, so it was left in place and is not part of
  this archive.

No active code or test may import from, read, or otherwise depend on this
directory at runtime, and no active code may be pointed here. Default pytest
discovery (`pyproject.toml`) excludes this tree. Archived tests and source are
historical records, not an executable package.

Archived Python files are historical source records, not an executable package.
Their old relative imports are not maintained after archival. Current code must
not import from this directory.

Mixed files were not moved. Their retained and obsolete portions are recorded
in `docs/partial_obsolescence_exceptions.md`. Existing Integration
Certification, PDDL transition, trace, verifier, Plan Provenance, Render
Production, Render Validation, state/frame pairing, curriculum, and planning
benchmark infrastructure remains in its original location.

Legacy datasets with active registry/test references also remain in place until
those references are migrated. No Attempt or Evidence Bundle was deleted.
