# Owner decision packet — does the calibration pilot need release-grade provenance?

**Plan:** `doc/high_level_plans/research_execution_plan.md`, Phase 3 (Gate 3) and Phase 0c
**Date:** 2026-08-07 · **HEAD:** `977cc65` · **Status:** one decision requested
**Companion to `DECISION.md` in this directory.** Read that first; this one is rulable only once
its decision 2 is settled. Nothing was implemented. Every number below is reproduced by
`derive_pilot_scope.py` in this directory.

---

## Why this is a separate packet

The archived `pipeline-state-audit-2026-08-07.md` note identified this as the
single biggest lever on the ~15–17 sessions between here and training start: Todos 5–10 exist to
produce an auditable production release, and a calibration pilot may need none of them. Bypassing
them halves the distance to training data.

Leverage is an argument for *deciding* it, not for bundling it with the contract. It is separate
because:

- **Its answer depends on the pilot's size, which `DECISION.md` decision 2 has not settled.** At 6
  instances the question is nearly moot; at 917 it answers itself.
- **It does not block v3.** v3 must ship, be implemented, and regenerate the corpus before this
  binds. Holding a contract decision over a provenance question that lands a milestone later would
  be expensive for no gain.

---

## The objection this packet has to survive

Stated plainly, because it is the strongest thing against the audit's recommendation:

> The pilot feeds **Gate 3**, which the plan calls a hard stop and the go/no-go for the whole method.
> A corpus built off the audited path carries weaker provenance for a decision that kills or
> continues the project. That is exactly the wrong place to economise.

The objection is sound in its premise and, I think, wrong in its conclusion. The argument follows.

---

## What Todos 5–10 actually contain

`derive_pilot_scope.py` checks the filesystem rather than the todo checkboxes:

| Todo | Module | Kind | Module | Test |
| --- | --- | --- | --- | --- |
| 5 | `cgas_production_review_packet` | release-process | MISSING | no |
| 6 | `cgas_partition_materialize` | correctness | MISSING | no |
| 7 | `cgas_production_staging` | release-process | MISSING | no |
| 8 | `cgas_certificates_alignment_binding` | correctness | MISSING | **yes** |
| 10 | `cgas_production_release` | release-process | MISSING | no |

**Correction to the pipeline audit.** That note records all five as "missing (no test either)".
Todo 8 has a test — `tests/phase3/test_cgas_certificates_alignment_binding.py`, 233 lines — and it
does not test a missing module. It tests `cgas_alignment.build_alignment` and
`cgas_certificates.build_steps` / `verify_steps`, all of which exist. **12 passed in 1.75 s.**

So Todo 8's property — certificates bound to the aligned render they were built against, rejecting
missing, malformed, and digest-mismatched alignment manifests — is **already implemented and already
green**. It does not need a new module. That is one of the two correctness items on the list, and it
is done.

## Correctness guards versus release-process guards

The distinction the audit's binary framing collapses. Of the five:

- **Todo 6** (`cgas_partition_materialize`) is genuinely correctness: it materializes the selected
  partition, and a pilot needs *something* to do this. But the fixture path already does it —
  `cgas_qwenvl.build_corpus(source_root, alignment_root, corpus_root)` is a working entry point that
  produced `data/planning_cgas_v1/qwenvl/{train,dev,test}.jsonl` end to end.
- **Todos 5, 7, 10** are release process: assemble a human review packet, stage before publication,
  publish atomically with rollback. These protect against *publishing a bad artifact to consumers*.
  They do not make the artifact more correct.

Every correctness invariant a pilot must not lose is enforced today, by modules that exist:

| invariant | enforced in | how |
| --- | --- | --- |
| replay-valid transitions | `cgas_alignment.py` | `build_alignment` rejects unproven replays |
| certificate re-derivation | `cgas_certificates.py` | `verify_steps` rebuilds every certificate from the trace and fails closed |
| no oracle leakage | `cgas_certificate_contracts.py` | `validate_model_input` against `ORACLE_FIELDS` |
| schema validity | `cgas_certificate_contracts.py` | `step_schema`, validated with `Draft202012Validator` |
| certificate ↔ alignment binding | `test_cgas_certificates_alignment_binding.py` | 12 tests over the existing modules — green |
| release digest immutability | `cgas_release_gate.py` | present and working |

---

## Why reproducibility is enough for Gate 3

**Gate 3's failure modes are asymmetric.** A false PASS sends the project on to build a production
corpus — expensive, but recoverable, and Gate 0c re-audits every row through the full path. A false
FAIL kills the method. The provenance question should therefore be judged on *which kind of defect
produces a false FAIL*.

A false FAIL comes from a pilot corpus that is **wrong**: mislabelled certificates, misaligned
images, leaked oracle fields, a non-representative instance mix. Every one of those is guarded by the
table above — by modules that exist and are tested. **None of them is guarded by a review packet, a
staging directory, or an atomic publish with rollback.** Release process protects the consumer of an
artifact; it does not protect the correctness of the measurement made from it.

**The pilot corpus is never published.** If Gate 3 passes, Phase 0c builds the production corpus
through the full audited path at the derived scale, and Gate 0c re-checks every row for a decodable
image, a replay-valid transition, and an accepted certificate. The pilot is an instrument, not a
release. A shortcut in it cannot reach a released artifact.

What Gate 3 does need is that its result can be **re-derived**: pinned inputs, a recorded
configuration digest, a manifest, and a deterministic build. That is reproducibility, and the
existing path already supplies it — the fixture corpus has a `source_manifest.jsonl`, a
`steps_manifest.json`, a `release_manifest.json`, and a digest pinned in tests.

**Where the objection is right, and what it should buy.** It is right that a go/no-go decision needs
to be defensible after the fact. That is bought by recording what the pilot was built from, not by
the release machinery. Hence the conditions below rather than a bare "skip Todos 5–10".

---

## The size dependency

Updated 2026-08-09 from the signed-v3 pilot-scope analysis at
`.claude/evidence/cgas-phase3-pilot-scope/`. The earlier table used a Phase A aggregate and
approximated expansion capacity as `2 * BFS expansions`; the canonical report now uses separate BFS
and IW yields per object count and applies an explicit diversity floor.

| harvest | ≥10/cell | ≥30/cell |
| --- | --- | --- |
| on-plan | 217–325 instances | **648–971 instances** |
| off-plan expansions, after diversity floor | **90 instances** | **94–111 instances** |

The existing 158 paired-exact candidates are insufficient for every on-plan alternative and
sufficient for every off-plan alternative. They pass the proposed floor: at least 30 candidates,
five composition signatures represented at least twice, three initial stack profiles, and three
goal-edge levels at each object count. The tightest object-count pool is 12 objects at 32 candidates.

The provenance recommendation is therefore actionable only together with the stability and harvest
rulings. No such ruling is recorded by this evidence.

---

## Recommendation

**Reproducibility, not release-grade — conditionally.** Build the pilot through the existing fixture
path (`build_corpus`), skipping Todos 5, 7, and 10, on four conditions:

1. **The pilot is never released.** It stays out of `data/planning_cgas_v1`, gets no release
   manifest, and is not consumable as training data for anything but the calibration baseline.
2. **Its inputs are pinned and recorded** — candidate ranks, checkpoint digest, trace contract and
   policy digests, render manifest digest — so the Gate 3 result is re-derivable from a manifest.
3. **`verify_steps` runs and passes on the pilot**, fail-closed, exactly as it does at fixture scale.
   This is the guard that actually protects Gate 3, and it costs nothing.
4. **Gate 3's result is provisional until Phase 0c re-derives it** on the production corpus at the
   derived scale. If the production corpus contradicts the pilot, the production corpus wins.

Todo 6's function is served by `build_corpus` for the pilot and should still be built properly for
Phase 0c. Todo 8 needs no module.

I hold this loosely on one point and firmly on another. Firmly: release process does not defend
against the failure mode that would kill the project, so paying for it here buys the wrong
insurance. Loosely: if off-plan harvesting is declined, the pilot is 217–971 instances and this
recommendation should be withdrawn rather than argued for.

**Decision requested:** approve or reject (1) the proposed `>=10 observations/cell` bar, (2) the
90-instance diversity floor above, (3) off-plan certificate harvesting, and, if all three are
approved, (4) reproducibility rather than release-grade provenance subject to conditions 1–4. No
owner approval is implied by this packet.
