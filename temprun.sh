source ~/cd_vlaplan && source .venv/bin/activate

TRACE_ROOT="outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round"

python scripts/phase3/generate_curriculum_trace_dataset.py \
  --bucket easy \
  --bucket medium \
  --domain blocksworld \
  --domain elevators \
  --domain ferry \
  --domain gripper \
  --domain logistics \
  --domain towers_of_hanoi \
  --planner gbfs \
  --planner ff \
  --planner iw \
  --planner graphplan \
  --jobs 4 \
  --output-root "$TRACE_ROOT"

sleep 10


source ~/cd_vlaplan && source .venv/bin/activate

TRACE_ROOT="outputs/phase3_curriculum_traces_visitall_strict_v1_1st_round"

python scripts/phase3/generate_curriculum_trace_dataset.py \
  --bucket easy \
  --bucket medium \
  --domain visitall \
  --planner gbfs \
  --planner ff \
  --planner iw \
  --planner graphplan \
  --jobs 4 \
  --planner-attempt-timeout-seconds 1200 \
  --domain-timeout-seconds 3600 \
  --output-root "$TRACE_ROOT"

sleep 10


source ~/cd_vlaplan && source .venv/bin/activate

TRACE_ROOT="outputs/phase3_curriculum_traces_15puzzle_easy_strict_v1_1st_round"

python scripts/phase3/generate_curriculum_trace_dataset.py \
  --bucket easy \
  --domain 15puzzle \
  --planner gbfs \
  --planner ff \
  --planner iw \
  --planner graphplan \
  --jobs 4 \
  --planner-attempt-timeout-seconds 1200 \
  --domain-timeout-seconds 3600 \
  --output-root "$TRACE_ROOT"


sleep 10

source ~/cd_vlaplan && source .venv/bin/activate

TRACE_ROOT="outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round"
FRAME_ROOT="outputs/phase3_planimation_frames_safe_no_visitall_$(date +%Y%m%d_%H%M%S)"

python scripts/phase3/generate_planimation_vlm.py \
  --dataset-root "$TRACE_ROOT" \
  --output-root "$FRAME_ROOT" \
  --bucket easy \
  --bucket medium \
  --domain blocksworld \
  --domain elevators \
  --domain ferry \
  --domain gripper \
  --domain logistics \
  --domain towers_of_hanoi \
  --render-only \
  --timeout-seconds 90 \
  --request-delay-seconds 1

sleep 10

source ~/cd_vlaplan && source .venv/bin/activate

TRACE_ROOT="outputs/phase3_curriculum_traces_visitall_strict_v1_1st_round"
FRAME_ROOT="outputs/phase3_planimation_frames_visitall_$(date +%Y%m%d_%H%M%S)"

python scripts/phase3/generate_planimation_vlm.py \
  --dataset-root "$TRACE_ROOT" \
  --output-root "$FRAME_ROOT" \
  --bucket easy \
  --bucket medium \
  --domain visitall \
  --render-only \
  --timeout-seconds 90 \
  --request-delay-seconds 1

sleep 10

source ~/cd_vlaplan && source .venv/bin/activate

TRACE_ROOT="outputs/phase3_curriculum_traces_15puzzle_easy_strict_v1_1st_round"
FRAME_ROOT="outputs/phase3_planimation_frames_15puzzle_easy_$(date +%Y%m%d_%H%M%S)"

python scripts/phase3/generate_planimation_vlm.py \
  --dataset-root "$TRACE_ROOT" \
  --output-root "$FRAME_ROOT" \
  --bucket easy \
  --domain 15puzzle \
  --render-only \
  --timeout-seconds 90 \
  --request-delay-seconds 1