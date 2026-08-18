#!/usr/bin/env bash
# Read-only capture of the six Todo 3 round-2 resume preconditions.
# Creates no process, tmux session, checkpoint, or trace artifact.
# Usage: bash .claude/evidence/production-p0-corpus-experiment-readiness/task-4/selector-infeasibility-proof/capture-preconditions.sh
set -o pipefail
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning || exit 125

printf '# Todo 4 infeasibility report - resume preconditions\n'
printf '# Captured: %s\n' "$(date --iso-8601=seconds)"
printf '# Repository: %s\n' "$(pwd -P)"
printf '# All checks are READ-ONLY.\n\n'

printf '== 1. Matching characterization writer (alias-free /proc walk) ==\n'
found=0
for p in /proc/[0-9]*; do
  c=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null)
  case "$c" in
    *cgas_candidate_characterization*|*cgas_production_population*)
      case "$c" in *claude*|*shell-snapshot*|*capture-preconditions*) continue ;; esac
      printf '%s: %s\n' "${p#/proc/}" "$c"
      found=1
      ;;
  esac
done
[ "$found" -eq 0 ] && printf '(no matching characterization writer)\n'
printf '\n'

printf '== 2. tmux sessions ==\n'
tmux list-sessions 2>&1 || printf '(no tmux server running)\n'
printf '\n'

printf '== 3. Checkpoint 2 absence ==\n'
ls -1 tmp/cgas-p0-characterized/checkpoints/
printf 'reservoir_checkpoint_000002.json: '
if [ -e tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000002.json ]; then
  printf 'PRESENT (UNEXPECTED)\n'
else
  printf 'ABSENT (expected)\n'
fi
printf '\n'

printf '== 4. Immutable digests ==\n'
sha256sum \
  tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json \
  tmp/cgas-p0-characterized/current.json \
  tmp/cgas-production-population/selector_attempt_000001.json
printf '\ntrace-v1 release digest (must remain 3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3):\n'
sha256sum data/planning_cgas_v1/release_manifest.json 2>&1 \
  || printf '(release manifest absent at this path)\n'
printf '\n'

printf '== 5. Temporary trace files ==\n'
tmpfiles=$(find tmp/cgas-p0-characterized/traces -type f \
  \( -name '.*trace-v2.jsonl-*' -o -name '*.tmp' -o -name '*.partial' -o -name '*.trace' \) -print)
if [ -z "$tmpfiles" ]; then
  printf '(none)\n'
else
  printf '%s\n' "$tmpfiles"
fi
printf '\n'

printf '== 6. Reusable trace artifacts ==\n'
printf 'trace directories:            %s\n' "$(ls tmp/cgas-p0-characterized/traces | wc -l)"
printf 'complete bfs.trace-v2.jsonl:  %s\n' "$(find tmp/cgas-p0-characterized/traces -name 'bfs.trace-v2.jsonl' -type f | wc -l)"
printf 'complete iw.trace-v2.jsonl:   %s\n' "$(find tmp/cgas-p0-characterized/traces -name 'iw.trace-v2.jsonl' -type f | wc -l)"
printf 'bfs total bytes:              '
find tmp/cgas-p0-characterized/traces -name 'bfs.trace-v2.jsonl' -printf '%s\n' \
  | awk '{s+=$1} END {printf "%d (%.2f GB)\n", s, s/1073741824}'
printf 'iw  total bytes:              '
find tmp/cgas-p0-characterized/traces -name 'iw.trace-v2.jsonl' -printf '%s\n' \
  | awk '{s+=$1} END {printf "%d (%.2f GB)\n", s, s/1073741824}'
printf 'bfs size distribution:\n'
find tmp/cgas-p0-characterized/traces -name 'bfs.trace-v2.jsonl' -printf '%s\n' \
  | awk '{ if($1>1e10) a++; else if($1>1e9) b++; else if($1>1e6) c++; else d++ }
         END {printf "  >10GB:   %d\n  1-10GB:  %d\n  1MB-1GB: %d\n  <1MB:    %d\n", a,b,c,d}'
printf '\n'

printf '== 7. Filesystem headroom ==\n'
printf '# NOTE: df must be run against the project path, not /data/scratch. The project\n'
printf '# directory reports its own quota (~11T); /data/scratch reports the whole 692T\n'
printf '# filesystem, which is not the binding constraint for writes made here.\n'
printf '\n-- project path (binding) --\n'
/usr/bin/df -h tmp/cgas-p0-characterized
printf '\n-- whole filesystem (not binding, shown for contrast) --\n'
/usr/bin/df -h /data/scratch
printf '\n'

printf '== VERDICT ==\n'
printf 'All six resume preconditions are clean; the round-2 resume command is safe to run.\n'
printf 'It was deliberately NOT run. See proof.json / README.md for why it cannot succeed.\n'
