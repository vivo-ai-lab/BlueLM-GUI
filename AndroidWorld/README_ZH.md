# 评测

基于 vLLM + Android 模拟器（android_world）的 GUI 智能体动态评测。

## 架构

```
评测进程 (main.py)
  ├─ 数据：通过模拟器接口动态获取（suite/reinitialize -> task_list -> task_length -> task/goal）
  ├─ 推理：调用 vLLM OpenAI 兼容 API（start_vllm.sh 独立启动）
  ├─ 模拟器：按端口直连（config.yaml emulator.port_min ~ port_max）
  └─ 输出：{output.dir}/{output.exp_name}/ 下保存轨迹 JSON + 截图 + 汇总
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | 评测主入口：加载配置、获取数据、并发评测、落盘 |
| `agent.py` | 单条轨迹交互逻辑：reset -> 循环[推理->解析->执行->截图]，动作解析 |
| `vllm_client.py` | vLLM 客户端：多模态消息转换 |
| `emulator_client.py` | 模拟器客户端：reset/step/score/close |
| `data_client.py` | 评测数据接口客户端（动态获取任务与指令） |
| `config.yaml` | 评测配置 |
| `start_vllm.sh` | 启动 vLLM 服务 |
| `run_eval.sh` | 一键运行评测 |

## 使用

```bash
# 1. 启动 vLLM（独立进程）
bash start_vllm.sh

# 2. 运行评测（评测进程按 config.yaml 中的端口直连模拟器）
bash run_eval.sh config.yaml
```

## 输出结构

```
output/{exp_name}/
├── trajectories/
│   ├── CameraTakePhoto.json        # 轨迹 JSON（含完整 messages）
│   ├── CameraTakePhoto/            # 同名截图文件夹
│   │   ├── screenshot_000.png
│   │   └── ...
│   ├── CameraTakeVideo.json
│   └── ...
├── summary.json                    # 汇总统计
└── results.csv                     # CSV 明细
```

## 关键配置

- `sampling.enable_thinking`：是否启用模型 thinking（false=关闭）
- `agent.img_win`：推理时保留的最近截图数（避免 prompt 超长）
- `data.timeout`：suite/reinitialize 接口超时
- `output.exp_name`：实验名称，隔离不同评测输出
