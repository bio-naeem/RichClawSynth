#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${ROOT_DIR}/outputs"

if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "${ROOT_DIR}/.env"
  set +a
fi

COUNT="${1:-10}"
TAG="${2:-demo}"
WORKERS="${WORKERS:-3}"
RETRIES="${RETRIES:-3}"
SEED="${SEED:-42}"
TOPICS_PATH="${TOPICS_PATH:-${ROOT_DIR}/references/topics_narrowed.txt}"

MODEL="${MODEL:-${OPENAI_MODEL:-glm-5.1}}"
API_BASE="${API_BASE:-${OPENAI_API_BASE:-https://open.bigmodel.cn/api/paas/v4/}}"
API_KEY="${API_KEY:-${OPENAI_API_KEY:-}}"
TIMEOUT="${TIMEOUT:-${OPENAI_TIMEOUT:-120}}"

if [ -z "${API_KEY}" ]; then
  echo "[error] OPENAI_API_KEY / API_KEY is empty. Fill it in ${ROOT_DIR}/.env first." >&2
  exit 1
fi

STEP1_OUT="${OUTPUT_DIR}/step1_hidden_plans_${COUNT}_${TAG}.jsonl"
STEP2_OUT="${OUTPUT_DIR}/step2_rewritten_${COUNT}_${TAG}.jsonl"
STEP3_OUT="${OUTPUT_DIR}/step3_naturalized_${COUNT}_${TAG}.jsonl"

mkdir -p "${OUTPUT_DIR}"

echo "[info] root=${ROOT_DIR}"
echo "[info] count=${COUNT} tag=${TAG}"
echo "[info] model=${MODEL}"

echo "[run] step1 -> ${STEP1_OUT}"
python "${ROOT_DIR}/step1_generate_hidden_plans.py" \
  "${COUNT}" \
  "${STEP1_OUT}" \
  "--workers" "${WORKERS}" \
  "--topics-path" "${TOPICS_PATH}" \
  "--seed" "${SEED}" \
  "--retries" "${RETRIES}" \
  "--timeout" "${TIMEOUT}" \
  "--model" "${MODEL}" \
  "--api-base" "${API_BASE}" \
  "--api-key" "${API_KEY}"

echo "[run] step2 -> ${STEP2_OUT}"
python "${ROOT_DIR}/step2_rewrite_richer.py" \
  "${STEP1_OUT}" \
  "${STEP2_OUT}" \
  --workers "${WORKERS}" \
  --retries "${RETRIES}" \
  --timeout "${TIMEOUT}" \
  --model "${MODEL}" \
  --api-base "${API_BASE}" \
  --api-key "${API_KEY}"

echo "[run] step3 -> ${STEP3_OUT}"
python "${ROOT_DIR}/step3_naturalize_diversify.py" \
  "${STEP2_OUT}" \
  "${STEP3_OUT}" \
  --workers "${WORKERS}" \
  --retries "${RETRIES}" \
  --timeout "${TIMEOUT}" \
  --model "${MODEL}" \
  --api-base "${API_BASE}" \
  --api-key "${API_KEY}"

echo "[run] step4 -> ${ROOT_DIR}/workspace_outputs/${TAG}"
python "${ROOT_DIR}/step4_build_workspaces.py" \
  "${STEP3_OUT}" \
  --tag "${TAG}" \
  --skills-pool "/data/mmwang35/skills-selected" \
  --force

echo "[done] outputs:"
echo "  step1: ${STEP1_OUT}"
echo "  step2: ${STEP2_OUT}"
echo "  step3: ${STEP3_OUT}"
echo "  step4: ${ROOT_DIR}/workspace_outputs/${TAG}/${TAG}-work"
