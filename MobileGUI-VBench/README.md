# MobileGUI-VBench

**MobileGUI-VBench** is a comprehensive benchmark built by **vivo AI Lab** for evaluating mobile GUI agent capabilities. It is part of the [BlueLM-GUI](https://github.com/vivo-ai/BlueLM-GUI) project — a real-device-centric flywheel for self-improving mobile GUI agents.

[![Hugging Face](https://img.shields.io/badge/Hugging%20Face-MobileGUI--VBench-orange.svg)](https://huggingface.co/datasets/vivo-ai/MobileGUI-VBench)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](../LICENSE)

## Overview

MobileGUI-VBench evaluates mobile GUI agents on **150 real-world tasks** across **40 real-world mobile apps** and **8 scenario categories**:

| Scenario | # Tasks |
| --- | --- |
| Video Streaming | 24 |
| Shopping & Deals | 24 |
| Lifestyle Services | 23 |
| Social & Communication | 21 |
| Travel & Transit | 18 |
| Music & Radio | 17 |
| Navigation | 17 |
| News & Reading | 6 |

## Key Features

- **Task diversity**: 142 single-app and 8 cross-app tasks.
- **Instruction complexity**: single-intent and multi-intent tasks with varying chain complexity (simple / medium / complex).
- **Instruction types**: explicit, implicit, and ambiguous instructions.
- **Preconditions & clarifications**: 65 tasks include environment preconditions, and 52 tasks require clarification-seeking behavior, testing the agent's ability to ask before acting.
- **Function coverage**: 77 distinct function points across 13 annotated dimensions.

## Dataset Contents

| File | Description |
| --- | --- |
| `MobileGUI-VBench.jsonl` | Task data in JSONL format (150 tasks) |
| `MobileGUI-VBench.xlsx` | Task data in Excel format |
| `MobileGUI-VBench-Doc.html` | Interactive documentation (English) |
| `MobileGUI-VBench-说明文档.html` | Interactive documentation (中文) |
| `MobileGUI-VBench_table.md` | Full benchmark comparison table |
| `evaluation_framework.pdf` | Evaluation framework report |

Each task record contains the following fields:

```json
{
  "task_id": 1,
  "query": "好久没上QQ了，看看朋友们最近都在发些什么动态",
  "scenario": "社交通讯",
  "involved_apps": "QQ",
  "precondition": "",
  "clarification_requirement": ""
}
```

- `task_id`: Unique task identifier
- `query`: Natural language instruction given to the agent
- `scenario`: One of the 8 scenario categories
- `involved_apps`: Apps required to complete the task (multiple apps separated by `、`)
- `precondition`: Environment state required before the task can be executed
- `clarification_requirement`: Whether and when the agent should ask for clarification

## Benchmark Results

| **Model** | **Params** | **MobileGUI-VBench** | **AndroidWorld** | **Access** |
| --- | --- | --- | --- | --- |
| **BlueLM-GUI (Ours)** | 35B-A3B | **87.4** | 84.9 | In-house |
| Seed2.1-Pro | - | 82.3 | 72.4 | Closed |
| Seed2.0-Pro | - | 80.8 | 71.5 | Closed |
| Seed2.0-Lite | - | 77.5 | 71.6 | Closed |
| Gemini3.7-Flash | - | 78.3 | 80.1 | Closed |
| Claude Opus 4.8 | - | 56.9 | 63.8 | Closed |
| GLM5.3-Flash | 320B-A18B | 66.4 | 78.4 | Open |
| Qwen3.8-Max | 2.4T-A95B | 64.2 | **85.3** | Open |
| Qwen3.8-Flash | 125B-A6B | 59.1 | 84.5 | Open |
| Qwen3.8-27B | 27B | 58.0 | 81.9 | Open |
| Qwen3.7-Plus | 397B-A17B | 49.6 | 81.0 | Closed |
| Qwen3.6-35B-A3B | 35B-A3B | 40.7 | 73.3 | Open |
| Qwen3.6-27B | 27B | 64.4 | 70.3 | Open |
| Qwen3.5-122B-A10B | 122B-A10B | 57.3 | 66.4 | Open |
| Qwen3.5-35B-A3B | 35B-A3B | 42.2 | 71.1 | Open |
| Qwen3.5-27B | 27B | 53.7 | 64.2 | Open |
| GUI-Owl-1.5-32B-Think | 32B | 47.1 | 71.6 | Open |
| UI-Venus-2.0-27B | 27B | - | 84.0 | Closed |
| UI-Venus-2.0-9B | 9B | 49.6 | 80.2 | Open |
| UI-Venus-1.5-30B-A3B | 30B-A3B | 24.1 | 77.6 | Open |
| PhoneBuddy | 4B | 39.0 | 83.2 | Open |
| UI-Tars-2.0 | 230B-A23B | - | 73.3 | Closed |
| MAI-UI-235B-A22B | 235B-A22B | - | 76.7 | Closed |
| Step-GUI | 8B | - | 80.2 | Closed |

## Access
- **Hugging Face**: [vivo-ai/MobileGUI-VBench](https://huggingface.co/datasets/vivo-ai/MobileGUI-VBench)

## Citation

If you use MobileGUI-VBench in your research, please cite:

```bibtex
@article{bluelm-gui,
  title   = {BlueLM-GUI Technical Report: A Real-Device-Centric Flywheel for Self-Improving Mobile GUI Agents},
  author  = {vivo AI Lab},
  journal = {arXiv preprint arXiv:2609.12394},
  year    = {2026},
  url     = {https://arxiv.org/abs/2609.12394}
}
```

## License

This dataset is released under the [Apache 2.0 License](../LICENSE).
