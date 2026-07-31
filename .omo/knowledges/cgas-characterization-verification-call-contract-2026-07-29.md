# CGAS Verification Call Contract

Phase 3 work verification is structural and must not call `_characterize`. Checkpoints carry a canonical row JSON string bound by `row_digest`; assembly builds the candidate from those verified rows. Candidate or final verification is the authoritative boundary and recomputes once per contract record. Publication must consume that candidate verification rather than rerunning final validation for anonymous or linked bundle bytes.
