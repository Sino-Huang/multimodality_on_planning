# Second-backbone evaluation (#103)

Second-backbone held-out evaluation for `expanded-second-backbone-v2` (panel `expanded-panel-v2-qualified`).

Outcome: **PASS**; complete coverage: True; model episodes 72/72; comparator episodes 144/72.

**Reduced scope (cost admission L1):** the executed panel is the 12 reference-cost-selected key-cell tasks, frozen before any model outcome; the frozen full panel is 72 model episodes. Selection: lowest reference bfs decision count only, frozen before any model outcome. Admission rationale: reduced key-cell panel selected by lowest reference bfs decision count only (tasks ranked by reference_costs.bfs.decisions; kept 12/24 tasks); documented fallback because L0 exceeded the branch remainder.

| Modality | Condition | Episodes | Successes | Decisions | Invalid ops | Model calls |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| multimodal-state | exact_reference | 24 | 24 | 640 | 0 | 0 |
| multimodal-state | pretrained_base | 12 | 0 | 12 | 12 | 12 |
| multimodal-state | process_sft | 12 | 0 | 18 | 12 | 18 |
| multimodal-state | random_valid | 24 | 18 | 634 | 0 | 0 |
| text-state | exact_reference | 24 | 24 | 640 | 0 | 0 |
| text-state | pretrained_base | 12 | 0 | 12 | 12 | 12 |
| text-state | process_sft | 12 | 0 | 23 | 12 | 23 |
| text-state | random_valid | 24 | 18 | 634 | 0 | 0 |
| visual-state | exact_reference | 24 | 24 | 640 | 0 | 0 |
| visual-state | pretrained_base | 12 | 0 | 12 | 12 | 12 |
| visual-state | process_sft | 12 | 0 | 18 | 12 | 18 |
| visual-state | random_valid | 24 | 18 | 634 | 0 | 0 |

All 72 model episodes were independently replayed; the 72 comparator episodes (random_valid, exact_reference) are sha256-pinned reused Goal-3 baseline episodes on identical tasks, never regenerated.

Compact evidence: [second-backbone-evaluation.json](second-backbone-evaluation.json) (byte-identical copy of the runtime evidence).
