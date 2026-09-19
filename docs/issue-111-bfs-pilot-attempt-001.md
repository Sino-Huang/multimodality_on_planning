# Issue #111 BFS pilot qualification attempt 001

**Outcome:** `VALID_STOP`

The deterministic issue-111 candidate qualifier inspected 4,446 generated train/dev candidates across all 15 governed domains. It rendered nothing, read or generated no test task, and enforced the fixed exact-BFS bands 1–64, 65–256, and 257–1024 with a ceiling of 500 candidates per domain and split.

Six of the required 90 cells were not filled:

- 15puzzle / train / medium
- 15puzzle / train / hard
- elevators / train / hard
- elevators / dev / hard
- sokoban / train / easy
- sokoban / dev / easy

The retained local evidence root is `outputs/bfs_pilot_v2/qualification-attempt-001`:

The selected manifest is intentionally empty because qualification did not pass. No v2 freeze manifest, authorization manifest, replay trace corpus, process corpus, LoRA smoke, or process-SFT run was created. Issue #54 remains blocked.
