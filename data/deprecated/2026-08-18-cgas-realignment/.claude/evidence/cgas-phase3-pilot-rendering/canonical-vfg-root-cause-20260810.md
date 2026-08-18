# Canonical Planimation VFG Root Cause - 2026-08-10

## Conclusion

No repository client defect was proven. The canonical request contract is correct, while the observed error localizes to the hosted Planimation backend's downstream planner path. No production code, endpoint fallback, retry fallback, synthetic VFG, or testing-only remote fixture was added.

## Authoritative request contract

- Backend route: `upload/(?P<filename>[^/]+)$`; `/upload/pddl` is valid because `pddl` is the route parameter.
- Required multipart fields: `domain`, `problem`, `animation`.
- The backend reads these values from `request.data` and does not inspect multipart filenames or per-part MIME types.
- Official client source uses the same tuples as the repository client: `(None, domain)`, `(None, problem)`, `(None, animation)`.
- Backend success returns a VFG JSON object containing fields including `visualStages`, `subgoalPool`, `subgoalMap`, `transferType`, and `imageTable`.

Sources:

- Backend route: https://github.com/planimation/backend/blob/develop/server/server/urls.py
- Backend handler: https://github.com/planimation/backend/blob/develop/server/app/views.py
- Planner: https://github.com/planimation/backend/blob/develop/server/app/vfg/parser/Plan_generator.py
- Official client: https://github.com/planimation/api-tools/blob/main/planimation_api.py
- VFG documentation: https://github.com/planimation/documentation/blob/master/docs/backend_dev_guide.md

Local comparison: `scripts/planimation_phase1_client.py::post_pddl_for_vfg` uses `/upload/pddl`, the required three fields, and `(None, text)` parts. Therefore filenames/MIME types and field names are not a verified defect.

## Failure localization

The recorded response was:

`API error: The process ends with an exception / Unexpected status from the server`

The authoritative backend wraps planner failures with `The process ends with an exception`. Its `Plan_generator.get_plan` raises `ValueError("Unexpected status from the server")` when the downstream solver response status is neither `ok` nor `PENDING`. The supported failure boundary is therefore: the request reached Planimation's planner invocation, whose downstream solver returned a non-success/non-pending status before the backend generated a VFG. This proves no multipart-contract defect, but the unavailable solver response does not distinguish service availability from solver-side domain/problem compatibility.

## Exact local input validation

The exact persisted derived problem is:

`outputs/image_frames/cgas-phase3-pilot-planimation-adapter-v1-smoke/state_cache/blocksworld/0322c69e499f0e2ba7161d25787a1260a275bd22382438a7f48e51e9da3737c4/c0e4e66599fadb608f6ddef3a64e6f33/problem.pddl`

The local parser accepted it with 8 objects, 12 initial atoms, 5 explicit goal atoms, no unsupported features, and 144 grounded actions. Local GBFS found a four-step solution:

1. `(unstack b04 b05)`
2. `(stack b04 b03)`
3. `(pickup b05)`
4. `(stack b05 b04)`

The bound domain is `modules/pddl-generators/blocksworld/4ops/domain.pddl`, and the bound profile is `data/pddl_instances/blocksworld/blocksworld_AP.pddl`. The profile supplies visual rules for `on`, `on-table`, and `holding`, matching the dynamic visualization predicates used by the domain. The only static concern is the unproven name difference `animation blocksworld` versus `domain blocksworld-4ops`; it is not identified by the server's planner-stage error.

## Decision and boundary

Do not edit `scripts/planimation_phase1_client.py`. A transport RED/GREEN test would be unjustified without a proven multipart-contract defect. Independent review identified a separate adapter provenance defect: the frozen state-only request has no canonical candidate binding for 4,293 shared-state groups, including 4,282 with distinct candidate goals. The adapter now rejects differing repeated source identities before network use rather than selecting the first index row. Therefore do not send a fresh smoke or start production until an owner-approved representative mapping or goal-independent VFG producer exists, even if external transmission is later authorized. The current command is retained as a deterministic checkpoint in `.claude/evidence/cgas-phase3-pilot-rendering/operator-command.md`, not as an executable production-ready command.
