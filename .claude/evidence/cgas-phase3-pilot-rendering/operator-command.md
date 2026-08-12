# Authorized Operator Command

> **⚠️ NOT EXECUTABLE — do not run.** The 2026-08-11 regression replays proved a repository-side
> remote compatibility delta (replay 2 fails, replay 3 succeeds with semantic init/goal preserved),
> so this command is **not authorized and not executable** until BOTH of the following pass:
> 1. the adapter/problem-writer patch to canonical `b1..bN` naming and July-compatible formatting
>    (RED→GREEN, then independent review and focused/regression/Ruff/basedpyright); AND
> 2. a canonicalized mapping-bound 8-object smoke AND a 12-object smoke with a non-empty locally
>    solvable representative goal, each passing full VFG→PNG→semantic/digest/provenance validation.
> Production 16,822-state rendering and 790-row replay alignment remain unstarted. Do not
> authorize/resume this command until the writer patch plus both valid smokes. See
> `verification-20260811-regression-replays.md` and
> `.handoff/2026-08-11-cgas-phase3-planimation-replay-classification.md`.

Do not execute this command without renewed authorization to transmit repository-derived PDDL/state data to `https://planimation.planning.domains` and a valid smoke result. The owner-approved representative mapping is now materialized locally and bound below; the prior authorized smoke still failed at the remote planner boundary. Retain this command only as the deterministic checkpoint until a fresh smoke is separately authorized and succeeds.

The command is both the initial production command and the crash-safe resume command. The adapter validates the frozen request/index digests and cardinalities before rendering, revalidates retained successes, rejects contract drift, appends and fsyncs each checkpoint record, and atomically republishes its manifest/report.

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
source ~/cd_vlaplan && python -m scripts.phase3.cgas_pilot_planimation_adapter /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-pilot-expansion-index-v1/missing-render-request.jsonl /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-pilot-expansion-index-v1/pilot-expansion-index.jsonl --repository-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning --output-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-phase3-pilot-planimation-adapter-v1 --domain-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/modules/pddl-generators/blocksworld/4ops/domain.pddl --profile-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/data/pddl_instances/blocksworld/blocksworld_AP.pddl --representative-mapping-path /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/tmp/cgas-phase3-pilot-representative-mapping-v1/representative-source-mapping.jsonl --expected-mapping-sha256 3d6ff222e3662319d9429e18e3bd0d33a7ea1aee67a07e6d9b1a25c506ad7de3 --expected-mapping-count 16822 --base-url https://planimation.planning.domains --timeout-seconds 30 --request-delay-seconds 0 --max-attempts 1 --production-contract
```

For each of 16,822 unique requested states, the renderer sends one multipart request containing the Blocksworld domain PDDL, a derived problem PDDL whose `:init` is the canonical requested state, and the Blocksworld animation profile. It does not send source traces, manifests, checkpoints, model data, credentials, or secrets. The remote service is expected to return VFG JSON; PNG generation and semantic validation then run locally.
