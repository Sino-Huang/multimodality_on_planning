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

- gate receipt SHA-256: `2591c96bddf5dd25b56e61e3048025120ab235d29f24cab4c85e5d3063b2beeb`
- qualification report SHA-256: `6910cb6d803db4ab5abf312c4cdf11357d77d61e8632fc1e4c30b8f960e22980`
- empty selected manifest SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

The selected manifest is intentionally empty because qualification did not pass. No v2 freeze manifest, authorization manifest, replay trace corpus, process corpus, LoRA smoke, or process-SFT run was created. Issue #54 remains blocked. The v1 freeze and authorization remain byte-identical at SHA-256 `5d00eb28c348c1d8a85472e834b52762683b0ddbbf9904c912bfaafdce6f23fd` and `6ddd28ca0586faadf13971b14af002ea6eefb1aacafb0a671a4eb70f06b7c8b7`, respectively.
