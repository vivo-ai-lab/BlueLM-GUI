# Dynamic Evaluation

Dynamic GUI-agent evaluation based on vLLM + Android emulators (android_world).

## Architecture

```
Evaluation process (main.py)
  ├─ Data: dynamically fetched via emulator APIs (suite/reinitialize -> task_list -> task_length -> task/goal)
  ├─ Inference: calls vLLM OpenAI-compatible API (started by start_vllm.sh)
  ├─ Emulator: direct connection by port (config.yaml emulator.port_min ~ port_max)
  └─ Output: saves trajectory JSON + screenshots + summary to {output.dir}/{output.exp_name}/
```

## Files

| File | Description |
|------|-------------|
| `main.py` | Evaluation entry point: loads config, fetches data, runs concurrent evaluations, writes results |
| `agent.py` | Single-trajectory interaction logic: reset -> loop [inference -> parse -> act -> screenshot], action parsing |
| `vllm_client.py` | vLLM client: multimodal message conversion |
| `emulator_client.py` | Emulator client: reset/step/score/close |
| `data_client.py` | Evaluation data client (dynamically fetches tasks and instructions) |
| `config.yaml` | Evaluation configuration |
| `start_vllm.sh` | Starts the vLLM service |
| `run_eval.sh` | One-click evaluation runner |

## Usage

```bash
# 1. Start vLLM (as a separate process)
bash start_vllm.sh

# 2. Run the evaluation (the process connects to emulators directly by port from config.yaml)
bash run_eval.sh config.yaml
```

## Output Structure

```
output/{exp_name}/
├── trajectories/
│   ├── CameraTakePhoto.json        # Trajectory JSON (with full messages)
│   ├── CameraTakePhoto/            # Screenshot folder named after the task
│   │   ├── screenshot_000.png
│   │   └── ...
│   ├── CameraTakeVideo.json
│   └── ...
├── summary.json                    # Summary statistics
└── results.csv                     # CSV details
```

## Key Configuration

- `sampling.enable_thinking`: whether to enable model thinking (false=disabled)
- `agent.img_win`: number of recent screenshots kept for inference (avoids overly long prompts)
- `data.timeout`: timeout for the suite/reinitialize API
- `output.exp_name`: experiment name, isolates different evaluation outputs
