# Cost admission for the unchanged 24-task panel

Both the maximum-allowance projection and a historical-consumption projection
will be reported. The four-algorithm, three-modality, 24-problem scope remains
unchanged; no task is selected using new model scores.

The current full-output text probe alone implies that the maximum-call/full-output
projection cannot fit the shared 56 GPU-hours. Each modality allows 17,240 model
calls across base and SFT. On GPU 0, the measured text reference-sized batch takes
52.41 seconds for two forced 384-token outputs. With a 1.25 margin, that is about
157 GPU-hours for text alone, before the other modalities. This upper-allowance
workload is explicitly infeasible under this branch allocation.

The completed v5 evaluation provides another measured basis: 1,625.63 aggregate
worker seconds for its complete 144 logical bindings, including model loading.
Its many early invalid-operation terminations consumed far less than its maximum
call/output allowances. The expanded panel has 4,310 exact-reference decisions,
versus 72 per modality in v5, a 59.86-fold increase in reference work.

`panel-cost-admission-v2.json` freezes a separate projection before any new final
model episode: multiply each modality's v5 worker duration by that reference-work
ratio, by at least one (or a larger measured current/historical per-call timing
ratio), and by 1.25. Before any slowdown adjustment this gives 33.79 GPU-hours.
Readiness and all qualification attempts are added from the shared ledger.

This estimate assumes historical termination/output-length behaviour remains a
useful workload proxy on the expanded tasks. It does **not guarantee completion
at every maximum allowance**. It does not authorize favourable retries, a smaller
matrix, a reset, a transfer or exceeding 56 GPU-hours. Goal 3 must retain all 1,152
logical bindings and report any missingness explicitly if the hard cap is reached.
The maximum-allowance and full-capacity projections remain visible even if this
conditional admission fits.

`finalize_expanded_panel.py` requires successful actual capacity probes on both
GPUs and all independent source, live-view, runtime-parity and common-memory
audits. It freezes the entire panel only if this separately declared historical
projection plus actual spending fits the unchanged cap. GPU results are still
being collected when this method is recorded; no final planning scores are used.
