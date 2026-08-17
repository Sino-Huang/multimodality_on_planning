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
