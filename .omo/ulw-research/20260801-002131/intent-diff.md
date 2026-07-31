# Intent Diff

| intent_id | expected truth | observed reality | diff | violated invariant | source | status |
|---|---|---|---|---|---|---|
| I1 | P0 corpus has trustworthy BFS/IW traces, aligned images, and accepted certificates | A release manifest exists and binds source, alignment, steps, Qwen, and loader evidence for 12 emitted rows | Pipeline proof exists, but scale/diversity is limited | Research readiness requires a corpus usable for calibration and structural OOD | proposal:194-201; release handoff:7-17 | partial |
| I2 | Calibration finds at least one recurrent certificate-localized failure before method training | No evidence inspected establishes a completed direct-VLA calibration run or recurrent failure matrix | Calibration gate remains open | execution plan:139-141 | violated |
| I3 | Main CGAS run follows calibration and frozen scaffold/route configuration | Memory, route labels, route calibration, calibration analysis, and CGAS training are explicitly deferred | Method work is not authorized yet | release handoff:9-11 | true |
| I4 | Structural OOD split has sufficient object/composition coverage | Current accepted release is 12 rows; prior characterization had only three composition signatures and one 12-object signature | OOD readiness is not demonstrated | partition approval:18-21 | violated |
| I5 | Future work starts from the authorized release manifest | Handoff names `data/planning_cgas_v1/release_manifest.json` as the sole downstream starting artifact | No diff | release handoff:5,15-17 | true |
