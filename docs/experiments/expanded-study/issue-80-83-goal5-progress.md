<!-- EXPANDED-GOAL5-ITERATION1-PROGRESS-V1 -->

Goal 5's iteration-one collection and replay stage is complete under `expanded-dagger-v1`.

- Text-state: 225 student decisions, 129 invalid attempts, 128 expert queries/corrections, 128 unique training corrections, and 12 independently replayed episodes.
- Visual-state: 219 student decisions, 129 invalid attempts, 128 expert queries/corrections, 128 unique training corrections, and 12 independently replayed episodes. All persisted on-policy scene assets are unlabelled 128px views.
- Multimodal-state: 215 student decisions, 129 invalid attempts, 128 expert queries/corrections, 128 unique training corrections, and 12 independently replayed episodes.
- Every cell stopped at the frozen correction quota after retaining one final rejected student output without an expert query. No quota was expanded or transferred, and no correction was invented or duplicated.
- Every correction is from the frozen training split and preserves raw student output, strict parse/runtime results, the identical expert input/view, last-valid Search Memory, and the accepted rollout-event link.
- Each independently reconstructed aggregation has exactly 512 records: 384 records from the fixed original BFS prefix followed by 128 genuine corrections, with 16 optimizer updates declared for the future Goal 6 update. Goal 5 ran zero training updates.
- Shared scheduler terminals and completion hooks passed for both GPU workers and the CPU final audit. Ports were GPU0/18800 and GPU1/18801. Cumulative DAgger consumption, including qualification and retained technical failures, is 2.220535196661949 of 48 GPU-hours.
- The affected suite passed 55 tests; lint passed.

Tracked evidence and content digests are in [`dagger-iteration-1.json`](https://github.com/Sino-Huang/multimodality_on_planning/blob/main/docs/experiments/expanded-study/dagger-iteration-1.json) and [`goal5-completion-audit.json`](https://github.com/Sino-Huang/multimodality_on_planning/blob/main/docs/experiments/expanded-study/goal5-completion-audit.json). The correction and aggregation datasets remain at the frozen `outputs/expanded-study/v1/dagger/collection/iteration-1/{modality}/` paths for Goal 6 and the later versioned release bundle.

This is an iteration-one progress milestone. Iteration two must be collected from the corresponding updated iteration-one policy and independently replayed in Goal 6/#84, so #80, #81, #82 and #83 remain open.
