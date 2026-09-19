Goal 4 is complete. The correction interface was implemented at `4ba554e535202dc1589a9c679128d4f116adeff8`, the outcome-blind protocol and jobs were frozen at `09aed2c`, and qualification evidence was published at `622786e45e169f14cf752d3534070b7098eb6896`.

- #78: invalid student output is strictly parsed and validated without mutating the last-valid Search Memory. The raw output, parse result, trusted rejection, charge, complete observable input and page binding are retained. The expert uses that identical pending input; its accepted action is separately linked and applied. Independent replay rejects hidden teacher fields, changed inputs, runtime drift and event-link drift.
- #79: BFS is fixed across text, visual and multimodal, with two sequential on-policy iterations, at most 512 student decisions and 128 corrections per modality/iteration, one seed (17), and final checkpoints only. Quota expires locally without invented or duplicated corrections.
- Each DAgger update uses all unique cumulative corrections plus an ordered original-SFT prefix for exactly 512 records, one epoch and 16 updates. Continued-SFT uses the unchanged original 512 records with identical exposure and its own matched checkpoint lineage.
- The estimand is explicitly within modality. Separately on-policy modality trajectories are not treated as paired evidence for a modality effect.
- Actual shared-scheduler qualification covered all three starting BFS adapters on both A100s. GPU 0 used `MASTER_PORT=18800`; GPU 1 used `MASTER_PORT=18801`. Prompt-only scalar/repeated-batch inference and discarded trainable-adapter steps passed without changing source checkpoints. All worker and final hooks passed.
- Qualification spent 0.141611 GPU-hours. The complete worst-case model-call allowance is explicitly infeasible at 234.941909 GPU-hours; the frozen historical-consumption admission is 35.458081/48 GPU-hours. No task or panel was removed, and the hard cutoff will preserve explicit missingness if realized calls exceed the estimate.
- Goal 4 collected zero corrections and performed zero persistent updates. Goals 5 and 6 own collection and scientific training.
- All 33 affected tests passed, including focused replay, split, quota, aggregation, hidden-teacher, serializer, conflict and target-budget checks.

Evidence:

- [Frozen protocol](https://github.com/Sino-Huang/multimodality_on_planning/blob/622786e45e169f14cf752d3534070b7098eb6896/configs/experiments/expanded-study/dagger-protocol.json)
- [Protocol rationale and commands](https://github.com/Sino-Huang/multimodality_on_planning/blob/622786e45e169f14cf752d3534070b7098eb6896/docs/experiments/expanded-study/dagger-protocol.md)
- [Hardware and cost qualification](https://github.com/Sino-Huang/multimodality_on_planning/blob/622786e45e169f14cf752d3534070b7098eb6896/docs/experiments/expanded-study/dagger-qualification.json)
- [Correction, replay and aggregation implementation](https://github.com/Sino-Huang/multimodality_on_planning/blob/4ba554e535202dc1589a9c679128d4f116adeff8/examples/planning_benchmark_slice/expanded_dagger.py)

The interface and freeze requirements in #78 and #79 are fulfilled. This closeout does not claim that #80–#84 collection, training or evaluation has run.
