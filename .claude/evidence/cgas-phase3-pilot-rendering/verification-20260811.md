# Phase 3 Pilot Rendering Verification - 2026-08-11

## Outcome

Red state. The owner authorized exactly one fresh mapping-bound Planimation smoke on 2026-08-11.
The adapter executed one canonical request with zero delay, one attempt, and a new output root, and
failed with the byte-identical downstream error already root-caused on 2026-08-10:

`API error: The process ends with an exception / Unexpected status from the server`

The representative-mapping milestone did not change the remote boundary. The client-side binding was
validated and passed end to end (mapping SHA pinned and matched, source row bound, run contract
computed), so the failure remains localized to the hosted Planimation backend's downstream planner
path, exactly as documented in `canonical-vfg-root-cause-20260810.md`. No VFG or PNG was returned.
The frozen 16,822-state production render and the 790-row replay alignment were therefore NOT started.

## Mapping-bound smoke (smoke-v2)

- Output root: `outputs/image_frames/cgas-phase3-pilot-planimation-adapter-smoke-v2` (new root; the
  pre-hardening `...-v1-smoke` directory was not resumed).
- Request subset: 1 row for state `00014e0bdfd513580c65f03b94e5c0a1487c34c7be37bd1fadf92bf9643e5f7f`;
  request JSONL SHA-256 `4500827235dd4fb9d3ea8c0637cf3c4ffd63fce4c018b7f31d4702b8421a898a`.
- Index subset: 2 rows for that state; index JSONL SHA-256 `daf81cee93f58000cee9903d54ef5b1e1e42d8ed5a1fa8fe4139961c8b951211`.
- Mapping: 1 row; mapping JSONL SHA-256 `e7703cb4faf05b69496dd244b545ee7171ab37f5abc419dad3d4af30059bb4bd`
  (pinned via `--expected-mapping-sha256`); report SHA-256 `1c45378b71fd70fd7bd8fea10eb013a06ff0599ca69c6531a0820e66eebefbcc`.
- Mapping-selected representative: row_id `cgas-pilot-expansion-20b7ac18577176c1fa927b68`,
  candidate `0322c69e499f0e2ba7161d25787a1260a275bd22382438a7f48e51e9da3737c4`, object_count 8,
  raw_rank 93, planner bfs, split train, replay_plan_member False, candidate_count 2. This matches
  what the frozen 16,822-row production mapping selects for this state under
  `replay_then_held_out_then_stable_source_v1`.
- Transmitted data (nothing else): 1,002-byte Blocksworld 4ops domain PDDL, one repository-derived
  8-object problem PDDL whose `:init` is the 12 canonical state atoms, and the 9,368-byte Blocksworld
  animation profile. No credentials, tokens, traces, manifests, checkpoints, model data, or secrets.
- Endpoint: `https://planimation.planning.domains/upload/pddl`; `--timeout-seconds 30`,
  `--request-delay-seconds 0`, `--max-attempts 1`.
- Counts: requested 1, processed 1, succeeded 0, failed 1, duplicate 0, collision 0, remaining 1.
- Run contract SHA-256: `880a79c99f35505385d63aaab1c8743de2384cae6415ee2168801020ad25b40b`.
- Client-side records (all validated): `domain_sha256 2eed94c5…79d81`,
  `problem_sha256 df2f5c26…880a6`, `profile_sha256 9ded071f…8d32`,
  `renderer_config_sha256 ad0ca46c…509b`, `source_record_sha256 37d284f8…6198`,
  `representative_mapping_sha256 e7703cb4…bb4bd` (matches pin).
- Cache key `341bb4e231155ae57d9195ac9ab2b5d6` was created; `result.json` records the failure. The
  derived `problem.pddl` was persisted in the state cache and in `candidate_problems/`.

## Verification

- Byte-identical error comparison vs the 2026-08-10 smoke: the single recorded attempt is
  `Failed to submit PDDL bundle. Attempts: https://planimation.planning.domains/upload/pddl -> API
  error: The process ends with an exception \n\n Unexpected status from the server` — the same core
  error pair, now with NO fallback attempts (the current adapter sends exactly one canonical request).
- Authoritative backend root cause unchanged: `Plan_generator.get_plan` raises
  `Unexpected status from the server` when the downstream solver returns neither `ok` nor `PENDING`.
- The derived problem remains locally valid: 8 objects, 12 initial atoms, 5 goal atoms, no
  unsupported features, 144 grounded actions, four-step GBFS solution (from 2026-08-10 root cause).
- The mapping milestone commit `f9a5081` is present on `main` and pushed to `origin/main`.

## Decision and boundary

- No production render was started: Phase 7 is gated on a fully valid smoke, and the smoke failed.
- No replay alignment was generated: its prerequisites (replay render coverage) were not met.
- No endpoint/candidate/request/retry/synthetic/cache/weakened-validator fallback was attempted.
- No further external request is authorized.
- Unblock requirement (exact): the hosted Planimation backend's downstream planner must return
  `ok`/`PENDING` for the submitted Blocksworld 4ops domain + 8-object problem + `blocksworld_AP`
  profile bundle, OR the owner must approve a goal-independent local VFG producer, before any
  production render can start.
