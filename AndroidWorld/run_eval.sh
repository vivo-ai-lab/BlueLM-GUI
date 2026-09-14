#!/bin/bash
# =============================================================================
# run_eval.sh — 一键运行动态评测
# =============================================================================
# 用法：
#   bash run_eval.sh [config_path]
# 示例：
#   bash run_eval.sh config.yaml
# =============================================================================

set -e
set -o pipefail

CONFIG=${1:-config.yaml}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR"

# 1. 检查 vLLM 服务（config.yaml 中的 api_url）
API_URL=$(python3 -c "
import yaml
with open('${CONFIG}') as f:
    cfg = yaml.safe_load(f)
print(cfg['model']['api_url'])
")
HEALTH_URL=${API_URL%/v1}/health
echo "[eval] 检查 vLLM 服务: ${HEALTH_URL}"
if ! curl -sf "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "[eval] vLLM 服务未启动，正在启动..."
    bash start_vllm.sh
else
    echo "[eval] vLLM 服务已就绪"
fi

# 2. 直连模式：使用 config.yaml 中的 host 和端口范围，直接连接模拟器
echo "[eval] 直连模式"

# 3. 运行评测（详细日志由 agent.py 写入 log/eval_{exp_name}.log，屏幕只显示进度）
LOG_DIR="$SCRIPT_DIR/log"
mkdir -p "$LOG_DIR"
EXP_NAME=$(python3 -c "
import yaml
with open('${CONFIG}') as f:
  cfg = yaml.safe_load(f)
print(cfg['output']['exp_name'])
")
export EVAL_LOG_DIR="$LOG_DIR"
export EVAL_EXP_NAME="$EXP_NAME"
echo "[eval] 开始评测: python main.py --config ${CONFIG}"
echo "[eval] 详细日志保存到: $LOG_DIR/eval_${EXP_NAME}.log"
python3 main.py --config "${CONFIG}"