"""单条评测轨迹的 Agent 交互逻辑。

流程：reset 模拟器 -> 循环 [模型推理 -> 解析动作 -> 模拟器执行 -> 刷新截图]，
直到 terminate / 达到最大轮数 / 解析失败终止。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from emulator_client import EmulatorClient, decode_screenshot


def _setup_logger() -> logging.Logger:
  logger = logging.getLogger("eval_detail")
  if logger.handlers:
    return logger
  logger.setLevel(logging.INFO)
  log_dir = Path(os.environ.get("EVAL_LOG_DIR", "log"))
  log_dir.mkdir(parents=True, exist_ok=True)
  exp_name = os.environ.get("EVAL_EXP_NAME", "default")
  handler = logging.FileHandler(log_dir / f"eval_{exp_name}.log", encoding="utf-8")
  handler.setFormatter(logging.Formatter("%(asctime)s - INFO - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
  logger.addHandler(handler)
  return logger


logger = _setup_logger()


VALID_ACTIONS = frozenset({
    "open", "click", "double_click", "long_press", "type",
    "swipe", "drag", "system_button", "wait", "answer",
    "take_notes", "terminate",
})

_FORMAT_RE = re.compile(
    r"(?:\s*response\s*)?"
    r"<tool_call>\s*(.*?)\s*</tool_call>\s*"
    r"<summary>.+?</summary>",
    re.DOTALL,
)
_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)


def parse_action(text: str) -> tuple[Optional[dict], bool]:
    """解析模型输出，返回 (动作 dict, 格式是否合法)。"""
    if not _FORMAT_RE.search(text):
        return None, False
    if not (text.count("<tool_call>") == 1 and text.count("</tool_call>") == 1):
        return None, False
    m = _TOOL_CALL_RE.search(text)
    if not m:
        return None, False
    try:
        tc = json.loads(m.group(1))
        args = tc.get("arguments", {})
        if not isinstance(args, dict):
            return None, False
        action_name = args.get("action")
        if action_name not in VALID_ACTIONS:
            return None, False
        return args, True
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None, False


def extract_parts(text: str) -> dict:
    """从模型输出中提取 think / action / summary 三部分（与参考评测日志对齐）。"""
    parts = {"think": "", "action": "", "summary": ""}
    m = re.search(r"thinking\s*(.*?)(?:\s*response|\s*<tool_call>)", text, re.DOTALL)
    if m:
        parts["think"] = m.group(1).strip()
    m = _TOOL_CALL_RE.search(text)
    if m:
        parts["action"] = m.group(1).strip()
    m = re.search(r"<summary>\s*(.*?)\s*</summary>", text, re.DOTALL)
    if m:
        parts["summary"] = m.group(1).strip()
    return parts


class TrajectoryResult:
    """一条轨迹的评测结果。"""

    def __init__(self, sample: dict):
        self.sample = sample
        self.success = False
        self.score = 0.0
        self.turns = 0
        self.actions: list[dict] = []
        self.screenshots: list[str] = []
        self.error: Optional[str] = None
        self.duration = 0.0
        self.raw_outputs: list[str] = []
        self.messages: list[dict] = []


async def run_trajectory(
    client: EmulatorClient,
    generate,
    sample: dict,
    system_prompt: str,
    cfg: dict,
) -> TrajectoryResult:
    """执行一条完整轨迹。

    Args:
        client: 已连接的模拟器客户端。
        generate: 异步生成函数 generate(messages) -> str。
        sample: 数据样本 dict。
        system_prompt: system prompt 文本。
        cfg: agent 配置段。
    """
    result = TrajectoryResult(sample)
    start = time.time()

    instruction = sample["prompt"][0]["content"]
    package = sample.get("package_name", "")
    seed = sample.get("seed")
    task_type = sample.get("task_type", "")
    task_idx = sample.get("task_id", 0)
    task_id = f"{task_type}_{task_idx}"
    logger.info(f"[task_id: {task_id}]: step=0, init task, query={instruction}")
    complexity_raw = sample.get("complexity")
    complexity = float(complexity_raw) if complexity_raw is not None else None

    if cfg.get("use_dynamic_turns", True) and complexity is not None and complexity > 0:
        max_turns = max(int(cfg.get("min_turns", 5)), int(complexity * cfg.get("complexity_multiplier", 10.0)))
    else:
        max_turns = int(cfg.get("max_turns", 50))

    messages = [{"role": "system", "content": system_prompt}]
    full_messages = [{"role": "system", "content": system_prompt}]
    img_win = int(cfg.get("img_win", 1))

    def _append_user_with_screenshot(text: str, screenshot: str) -> None:
        """追加带截图的 user 消息。"""
        messages.append({"role": "user", "content": text, "images": [screenshot]})
        img_msgs = [m for m in messages if m.get("images")]
        if len(img_msgs) > img_win:
            oldest = img_msgs[0]
            oldest.pop("images", None)
        full_messages.append({"role": "user", "content": text, "images": [screenshot]})

    def _append_assistant(text: str) -> None:
        """追加 assistant 消息到两个消息列表。"""
        content = text if text.startswith("<think>\n") else "<think>\n" + text
        messages.append({"role": "assistant", "content": content})
        full_messages.append({"role": "assistant", "content": content})

    try:
        screenshot_b64 = None
        last_reset_err = None
        for attempt in range(1, 6):
            try:
                screenshot_b64 = await client.reset(instruction, package, seed, task_type, task_idx)
                if screenshot_b64:
                    break
                last_reset_err = "reset 返回空截图"
            except Exception as e:
                last_reset_err = str(e)
            print(f"[agent] reset 失败 (attempt {attempt}/5): {last_reset_err}")
            await asyncio.sleep(2)
        if not screenshot_b64:
            raise RuntimeError(f"reset 重试 5 次仍失败: {last_reset_err}")

        result.screenshots.append(screenshot_b64)
        _append_user_with_screenshot(f"{instruction}", screenshot_b64)

        for turn in range(1, max_turns + 1):
            generated = await generate(messages)
            result.raw_outputs.append(generated)
            parts = extract_parts(generated)
            logger.info(f"[task_id: {task_id}]: step={turn - 1}, answer: {generated}")
            action, is_valid = parse_action(generated)

            if not is_valid:
                result.error = "解析失败"
                logger.info(f"[task_id: {task_id}]: step={turn - 1}, 解析失败, raw_output={generated!r}")
                _append_assistant(generated)
                break

            result.actions.append(action)
            result.turns = turn
            _append_assistant(generated)
            logger.info(f"[task_id: {task_id}]: step={turn - 1}, think: {parts['think']}")
            logger.info(f"[task_id: {task_id}]: step={turn - 1}, action: {parts['action']}")
            logger.info(f"[task_id: {task_id}]: step={turn - 1}, summary: {parts['summary']}")

            if action["action"] == "take_notes":
                continue

            screenshot_b64 = await client.step(action)
            if not screenshot_b64:
                result.error = f"step {turn} 返回空截图"
                break
            result.screenshots.append(screenshot_b64)
            _append_user_with_screenshot(f"{instruction}", screenshot_b64)

            if action["action"] in ("terminate", "answer"):
                break

        result.score = await client.get_score(task_type, task_idx) or 0.0
        result.success = result.score > 0
        logger.info(f"[task_id: {task_id}]: 轨迹结束, turns={result.turns}, score={result.score}, success={result.success}, error={result.error}")

    except Exception as e:
        result.error = str(e)
    finally:
        await client.close_app()
        result.duration = time.time() - start
        result.messages = full_messages

    return result