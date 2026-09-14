#!/bin/bash
# =============================================================================
# start_vllm.sh — 启动 vLLM OpenAI 兼容服务（独立进程）
# =============================================================================
# 用法：
#   bash start_vllm.sh
# =============================================================================

set -e

# ============== 路径配置 ==============
# vLLM 可执行环境
VLLM_VENV=${VLLM_VENV:-/path/to/vllm/venv/bin}

# 模型路径（SFT checkpoint）
MODEL_PATH=${MODEL_PATH:-/path/to/model/checkpoint}
MODEL_NAME=${MODEL_NAME:-mobileGUI}

# ============== 服务配置 ==============
PORT=${PORT:-10005}
TP=${TP:-2}
DTYPE=${DTYPE:-bfloat16}
MAX_NUM_SEQS=${MAX_NUM_SEQS:-8}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-16384}

LOG_FILE=${LOG_FILE:-$(dirname "$0")/vllm.log}
START_TIMEOUT=${START_TIMEOUT:-6000}

echo "[vllm] 启动 vLLM 服务: $MODEL_PATH"
echo "[vllm] 端口=$PORT TP=$TP max_model_len=$MAX_MODEL_LEN"
echo "[vllm] 日志: $LOG_FILE"

# 清理旧日志
: > "$LOG_FILE"

nohup "$VLLM_VENV/vllm" serve "$MODEL_PATH" \
    --served-model-name "$MODEL_NAME" \
    --tensor-parallel-size "$TP" \
    --dtype "$DTYPE" \
    --max-num-seqs "$MAX_NUM_SEQS" \
    --max-model-len "$MAX_MODEL_LEN" \
    --port "$PORT" \
    > "$LOG_FILE" 2>&1 &

VLLM_PID=$!
echo "[vllm] PID=$VLLM_PID"

# 等待服务就绪
echo "[vllm] 等待服务就绪 (超时 ${START_TIMEOUT}s)..."
for i in $(seq 1 ${START_TIMEOUT}); do
    if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
        echo "[vllm] 服务已就绪 (${i}s)"
        exit 0
    fi
    sleep 1
done

echo "[vllm] ERROR: 服务启动超时，请查看 $LOG_FILE"
exit 1