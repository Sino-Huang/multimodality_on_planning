# Authorized Operator Command

> **⚠️ NOT EXECUTABLE — do not run. Superseded backend path.** On 2026-08-12 the owner selected
> the pinned local `planimation/backend` commit `94d82afb5ee122ce579dd11ca1953b7c85ca5824`
> (`v0.1.7`) as the production backend target for the two required smokes. This hosted command is
> therefore superseded as the selected backend path and remains **not authorized and not
> executable**. The adapter/problem-writer patch to canonical `b1..bN` naming and July-compatible
> formatting is complete, tested, reviewed, and integrated (`b9e2e65`, Ruff closure `020b812`); it
> must not be reopened. The remaining gate before any render is: validate the integrated
> adapter/`StateRenderer` against localhost, then pass a mapping-bound 8-object smoke AND a
> 12-object smoke with a non-empty locally solvable representative goal through the localhost
> production path, each passing full VFG→PNG→semantic/digest/provenance validation, with one
> bounded execution path, no hosted request, and no hosted fallback. Those smokes are defined in
> prose only (see `backend-selection-decision-packet-20260812.md`) and require separate execution
> authorization. Production 16,822-state rendering and 790-row replay alignment remain unstarted;
> coverage is 0/16,822. Even if both smokes pass, the 16,822-state render requires a further
> separate owner/operator decision. See `verification-20260811-regression-replays.md` and
> `.handoff/2026-08-11-cgas-phase3-planimation-replay-classification.md`.

Do not execute this command. It transmits repository-derived PDDL/state data to
`https://planimation.planning.domains` and is superseded as the selected backend path: the pinned
local backend (`94d82afb…`, v0.1.7) was selected on 2026-08-12. The owner-approved representative
mapping remains materialized and bound below. No executable localhost command is provided here; the
localhost production-path smokes are defined as a prose milestone only in
`backend-selection-decision-packet-20260812.md` and require separate execution authorization. Retain
this command only as the superseded deterministic checkpoint record; do not resume it.

The command is both the initial production command and the crash-safe resume command. The adapter validates the frozen request/index digests and cardinalities before rendering, revalidates retained successes, rejects contract drift, appends and fsyncs each checkpoint record, and atomically republishes its manifest/report.

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
source ~/cd_vlaplan && python -m scripts.phase3.cgas_pilot_planimation_adapter /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-pilot-expansion-index-v1/missing-render-request.jsonl /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-pilot-expansion-index-v1/pilot-expansion-index.jsonl --repository-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning --output-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-phase3-pilot-planimation-adapter-v1 --domain-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/modules/pddl-generators/blocksworld/4ops/domain.pddl --profile-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/data/pddl_instances/blocksworld/blocksworld_AP.pddl --representative-mapping-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-pilot-representative-mapping-v1/representative-source-mapping.jsonl --expected-mapping-sha256 3d6ff222e3662319d9429e18e3bd0d33a7ea1aee67a07e6d9b1a25c506ad7de3 --expected-mapping-count 16822 --base-url https://planimation.planning.domains --timeout-seconds 30 --request-delay-seconds 0 --max-attempts 1 --production-contract
```

For each of 16,822 unique requested states, the renderer sends one multipart request containing the Blocksworld domain PDDL, a derived problem PDDL whose `:init` is the canonical requested state, and the Blocksworld animation profile. It does not send source traces, manifests, checkpoints, model data, credentials, or secrets. The remote service is expected to return VFG JSON; PNG generation and semantic validation then run locally.
