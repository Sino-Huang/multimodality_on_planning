---
slug: planimation-hybrid-traversal-rendering
status: plan-written
intent: clear
pending-action: await user decision to start execution or request high-accuracy review
approach: hybrid plan-replay plus search-traversal supervision with strict concrete-state and release contracts
---

# Draft: planimation-hybrid-traversal-rendering

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
| source snapshot | immutable four-root JSONL provenance | active | outputs/phase3_curriculum_traces_* |
| trace adapters | strict GBFS/FF/IW/Graphplan traversal projections | active | scripts/phase3/{gbfs,local_planners,local_iw,local_graphplan}.py |
| state rendering | derived-PDDL Planimation frames with strict cache/image checks | active | scripts/phase3/planimation_pairing.py; src/data_collect/rendering.py |
| hybrid records | separate plan replay and traversal JSONL outputs | active | scripts/phase3/planimation_pairing.py |
| release gates | complete production verification and staged rollout | active | scripts/phase3/verify_planimation_vlm.py |

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->
| Graphplan layers are not concrete states | retain them as nonvisual traversal events; render only extracted-plan replay states | Planimation needs complete PDDL state atoms | no |
| successor state availability | deterministically apply normalized action only when trace supplies selected concrete state | preserves symbolic validity | no |
| source root | freeze current non-deprecated outputs rather than stale legacy data root | current corpus has active GBFS identifiers | no |

## Findings (cited - path:lines)

- `render_replay_states()` currently consumes only final-plan replay transitions; `_render_one_state()` can render arbitrary complete state atoms through derived PDDL rewriting (`scripts/phase3/planimation_pairing.py`).
- FF records selected and successor state atoms; GBFS/IW records selected states but require deterministic successor reconstruction; Graphplan stores planning-graph layers rather than concrete nodes (current output inspection and planner modules).
- Current verifier/cache/image checks are insufficient for production: missing JSONL can appear valid, cache hits are shallow, PNG checks are signature-only, and raw Graphplan cannot be rendered as concrete state.
- Metis review found stale standalone trace-file dependencies, strict-schema gaps, cache/profile portability gaps, unsafe ZIP extraction, and zero-action/partial-output edge cases requiring explicit plan gates.

## Decisions (with rationale)

- Use `plan_replay` and `search_traversal` as explicit supervision modes; shared state assets never imply shared event semantics.
- Replace `traces/**.full_example.json` loading with source JSONL path/line/example/hash provenance.
- Reject legacy `bfs` source snapshots rather than silently mapping to `gbfs`.
- Treat historical Planimation frames as diagnostic only; all training images derive from validated state PDDL.

## Scope IN

- Provenance snapshot, adapters, event/schema contracts, rendering/cache/image hardening, hybrid record emission, verifier modes, canaries, and documentation.

## Scope OUT (Must NOT have)

- Planner search changes, source-root mutation, fabricated Graphplan concrete states, legacy silent aliases, and corpus-scale rendering before gates pass.

## Open questions

## Approval gate
status: approved by user on 2026-07-15; plan written
<!-- When exploration is exhausted and unknowns are answered, set status: awaiting-approval. -->
<!-- That durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->
