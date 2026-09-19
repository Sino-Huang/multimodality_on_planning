# Second-backbone qualification (#101-#103)

Second-backbone input qualification for `expanded-second-backbone-v2` (backbone `internvl3_5-8b`).

Outcome: **PASS** (complete: True).

| Modality | Max train prefix | Max train full | Max live |
| --- | ---: | ---: | ---: |
| text-state | 2106 | 2240 | 4421 |
| visual-state | 11527 | 11673 | 16538 |
| multimodal-state | 12553 | 12706 | 18289 |

- Context tokens: 32768; output tokens: 384.
- Tokenizer identity (InternVL vs Qwen templated ids): True.
- Records measured: 1536; tasks measured: 24; decisions measured: 5907.
- Violations: 0; verify_complete cross-checks: 3; processed-pixel previews: 6.

Compact evidence: [second-backbone-qualification.json](second-backbone-qualification.json) (byte-identical copy of the runtime report).
