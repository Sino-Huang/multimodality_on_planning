# Phase 3 Live Output Root Consumers

New curriculum-trace generation defaults to `outputs/reasoning_traces/curriculum`.
The approved safe-no-Visitall trace dataset remains under `outputs/reasoning_traces/curriculum`.
The retained Visitall and 15-puzzle datasets are consumed from `outputs/deprecated/phase3/curriculum_traces`; they must not be recreated below `outputs/reasoning_traces`.
`temprun.sh --help` and unsupported arguments must exit before the workflow starts.
