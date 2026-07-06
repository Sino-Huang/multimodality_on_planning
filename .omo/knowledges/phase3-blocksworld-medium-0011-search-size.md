# Phase 3 Blocksworld Medium 0011 Search Size

Measured for `data/curriculum_pddl/blocksworld/train/medium/blocksworld-train-medium-0011` after raising Phase 3 local defaults to IW(3) and Graphplan expansion cap `100000`.

- Objects: 8 blocks.
- Grounded actions: 144.
- Ground atom universe in grounded task: 89.
- Initial state atoms: 12.
- Goal atoms: 4.
- Initial applicable actions: 3.
- Legal Blocksworld state upper bound used for difficulty discussion: 394,353 empty-hand stack states; 695,417 when including one-block holding states.
- BFS found a replay-valid plan of length 10 after expanding 3,341 states, visiting 7,548 states, and generating 13,947 applicable edges before the goal parent.
- BFS branching along the explored prefix averaged 4.174 applicable actions per expanded state, with max 8 observed; max frontier before the goal was 4,207.
- Graphplan local trace succeeded with selected goal layer 4, 6 proposition layers, 5 action layers, and 13,544 action-mutex pair entries.
- FF-style local trace, IW(3), and Graphplan all emitted `success_full_trace`; IW(1) and IW(2) remain insufficient for this exact instance.

Verification command for default local trace collection:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-train-medium-0011 --planner bfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_bwm0011_default_local_verify --quiet
```

Expected signal: `attempt_status_summary: {"success_full_trace": 4}` and `extracted_trace_count: 4`.
