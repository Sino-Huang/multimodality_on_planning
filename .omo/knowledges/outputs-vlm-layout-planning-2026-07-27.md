# Outputs VLM layout planning knowledge

- Requested end state: `outputs/reasoning_traces/`, `outputs/image_frames/`, and `outputs/deprecated/` are the only top-level output categories.
- The approved pilot contains nine VLM JSONLs totaling 14,473,377 bytes. The owner selected physical copies in `reasoning_traces/vlm_records/`, not symlinks.
- The hidden `.output_reorganization_20260726.json.txn` and `.swap` files are a matching prepared transaction: transaction SHA-256 references the 12,362-byte swap payload. They are migration evidence, not invalid reasoning traces or image frames.
- GPFS rejected `renameat2(..., RENAME_NOREPLACE)` before any data-root move. Future execution must use a lock-guarded same-device ordinary rename fallback and append-only receipt journals.
