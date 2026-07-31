# CGAS Trusted State GPFS

- The shared repository `tmp` is only a current-owner, non-group/other-writable parent. CGAS state is pinned under `tmp/.cgas-characterization` at exact owner mode 0700.
- Fresh creates the state child and private root descriptor-relatively. Read-only verification does not create state. Old direct-`tmp` lifecycle names reject without adoption.
- The final publisher accepts the live trusted-state descriptor, not shared `tmp`.
- Synthetic 481 checkpoint fill measured 13.25 minutes; real owner review is expected to take 12-16 minutes plus finalize and final verification.
