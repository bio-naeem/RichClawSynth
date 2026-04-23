#!/bin/bash

set -u

PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
PID_DIR="${LOG_DIR}/pids"
RUN_TS="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$LOG_DIR" "$PID_DIR"

HUB="${1:-}"
BASE="${2:-}"
RESULTS="${3:-}"

ARGS=""
if [ -n "$HUB" ]; then ARGS="$ARGS --hub $HUB"; fi
if [ -n "$BASE" ]; then ARGS="$ARGS --base $BASE"; fi
if [ -n "$RESULTS" ]; then ARGS="$ARGS --results $RESULTS"; fi

SCRIPTS=(
  "/data/mmwang35/gpt-exp/step5_file_generate.py$ARGS"
)

for script_with_args in "${SCRIPTS[@]}"; do
  # Split into script path and args
  script=$(echo "$script_with_args" | awk '{print $1}')
  extra_args=$(echo "$script_with_args" | cut -d' ' -f2-)
  
  if [[ ! -f "$script" ]]; then
    echo "Skip: file not found: $script"
    continue
  fi

  name="$(basename "$script" .py)"
  log_file="$LOG_DIR/${name}_${RUN_TS}.log"
  pid_file="$PID_DIR/${name}.pid"

  # Run with extra args if present, splitting correctly
  if [ "$script_with_args" == "$script" ]; then
    nohup "$PYTHON_BIN" -u "$script" >"$log_file" 2>&1 &
  else
    nohup "$PYTHON_BIN" -u $script_with_args >"$log_file" 2>&1 &
  fi
  pid=$!
  echo "$pid" >"$pid_file"

  echo "Started $script"
  echo "  PID: $pid"
  echo "  Log: $log_file"
  echo "  PID file: $pid_file"
done
