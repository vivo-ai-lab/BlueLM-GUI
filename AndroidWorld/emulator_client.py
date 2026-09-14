"""模拟器（Android AVD）异步 HTTP 客户端 - 直连模式。

直接调用模拟器裸接口（android_server.py 的 A 协议）：
  POST /reset?go_home=true               -> {"status": "success"}
  GET  /screenshot?wait_to_stabilize=True -> {"pixels": "<base64>"}
  POST /execute_action  {action_type,..} -> {"status": "success"}
  POST /close                             -> {"status": "success"}
  GET  /task/score?task_type=..&task_idx=.. -> {"score": float}
"""
from __future__ import annotations

import asyncio
import base64
import re
from typing import Any, Optional

import aiohttp
from PIL import Image


def escape_adb_text(text: Optional[str]) -> Optional[str]:
    """对 adb shell input text 的文本做空格转义（空格 -> %s）。"""
    if text is None:
        return None
    return text.replace(" ", "%s")


COORD_SCALE = 1000.0  # 模型输出的坐标量程（0~1000 相对坐标）


def scale_coordinates(action: dict, width: int, height: int) -> dict:
    """把模型输出的 0~1000 相对坐标转换为实际像素坐标。"""
    for key in ("coordinate", "start_coordinate", "end_coordinate"):
        coord = action.get(key)
        if isinstance(coord, (list, tuple)) and len(coord) == 2 and all(v is not None for v in coord):
            action[key] = [
                round(coord[0] * width / COORD_SCALE),
                round(coord[1] * height / COORD_SCALE),
            ]
    return action


def convert_action_to_android(action: dict) -> Any:
    """把动作 dict 转换为模拟器 android 扁平动作（或动作序列）。"""
    name = (action.get("action") or "").strip()
    coord = action.get("coordinate") or [None, None]
    start = action.get("start_coordinate") or [None, None]
    end = action.get("end_coordinate")

    if name in ("click", "double_click"):
        return {"action_type": "click", "x": coord[0], "y": coord[1]}
    if name == "long_press":
        return {"action_type": "long_press", "x": coord[0], "y": coord[1]}
    if name in ("swipe", "drag") and all(v is not None for v in start + end):
        return {"action_type": "swipe", "x": start[0], "y": start[1], "x2": end[0], "y2": end[1]}
    if name == "type":
        text = escape_adb_text(action.get("text"))
        if coord and coord[0] is not None:
            return [
                {"action_type": "click", "x": coord[0], "y": coord[1]},
                {"action_type": "input_text", "text": text, "clear_text": False},
            ]
        return {"action_type": "input_text", "text": text, "clear_text": False}
    if name == "system_button":
        mapping = {"back": "navigate_back", "home": "navigate_home", "enter": "keyboard_enter"}
        return {"action_type": mapping.get(action.get("button"), "wait")}
    if name == "open":
        return {"action_type": "open_app", "app_name": action.get("text")}
    if name == "wait":
        return {"action_type": "wait"}
    if name == "terminate":
        return {"action_type": "status", "goal_status": "complete"}
    if name == "answer":
        return {"action_type": "answer", "text": action.get("text", "")}
    return {"action_type": "status", "goal_status": "infeasible"}


def decode_screenshot(b64: str) -> Image.Image:
    """把 base64 截图解码为 PIL Image。"""
    if b64.startswith("data:image"):
        b64 = b64.split(",", 1)[1]
    return Image.open(__import__("io").BytesIO(base64.b64decode(b64))).convert("RGB")


class EmulatorClient:
    """单台模拟器的异步客户端（直连模式，A 协议）。"""

    def __init__(self, host: str, timeout: int = 240, max_retry: int = 3):
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.max_retry = max_retry
        # 当前截图实际尺寸（像素），reset 时获取，step 坐标转换用
        self.screen_size: Optional[tuple[int, int]] = None

    async def _post(self, path: str, params: dict) -> dict:
        """POST 请求，参数走 URL query。"""
        from urllib.parse import urlencode
        base = self.host if self.host.startswith("http://") else f"http://{self.host}"
        url = f"{base}{path}?{urlencode(params)}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            for attempt in range(self.max_retry):
                try:
                    async with session.post(url) as resp:
                        resp.raise_for_status()
                        return await resp.json()
                except Exception as e:
                    if attempt == self.max_retry - 1:
                        raise RuntimeError(f"POST {path} failed after {self.max_retry} tries: {e}")
                    await asyncio.sleep(1 + attempt)

    async def _post_json(self, path: str, body: dict) -> dict:
        """POST 请求，body 走 JSON（用于 execute_action 等需要 JSON body 的接口）。"""
        base = self.host if self.host.startswith("http://") else f"http://{self.host}"
        url = f"{base}{path}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            for attempt in range(self.max_retry):
                try:
                    async with session.post(url, json=body) as resp:
                        resp.raise_for_status()
                        return await resp.json()
                except Exception as e:
                    if attempt == self.max_retry - 1:
                        raise RuntimeError(f"POST {path} failed after {self.max_retry} tries: {e}")
                    await asyncio.sleep(1 + attempt)

    async def _get(self, path: str, params: dict) -> dict:
        """GET 请求，参数走 URL query。"""
        from urllib.parse import urlencode
        base = self.host if self.host.startswith("http://") else f"http://{self.host}"
        url = f"{base}{path}?{urlencode(params)}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            for attempt in range(self.max_retry):
                try:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        return await resp.json()
                except Exception as e:
                    if attempt == self.max_retry - 1:
                        raise RuntimeError(f"GET {path} failed after {self.max_retry} tries: {e}")
                    await asyncio.sleep(1 + attempt)

    async def _fetch_screenshot(self) -> str:
        """获取当前截图 base64。"""
        data = await self._get("/screenshot", {"wait_to_stabilize": "True"})
        pixels = data.get("pixels") if isinstance(data, dict) else data
        if not pixels:
            raise RuntimeError("截图返回空")
        screenshot = pixels if isinstance(pixels, str) else ""
        if screenshot:
            try:
                self.screen_size = decode_screenshot(screenshot).size
            except Exception:
                self.screen_size = None
        return screenshot

    async def reset(self, query: str, package: str, seed: int, task_type: str, task_idx: int = 0) -> str:
        """重置模拟器环境，初始化任务，返回首屏截图 base64。

        完整流程：
          1. POST /reset?go_home=true  重置环境
          2. GET /suite/reinitialize?seed=..  重建任务 suite
          3. POST /task/initialize?task_type=..&task_idx=..  初始化任务
          4. GET /screenshot  获取首屏截图
        """
        # 1. 重置环境
        await self._post("/reset", {"go_home": True})
        # 2. 重建任务 suite
        if seed is not None:
            await self._get("/suite/reinitialize", {
                "n_task_combinations": "1",
                "seed": str(seed),
                "task_family": "android_world",
            })
        # 3. 初始化任务
        if task_type:
            await self._post("/task/initialize", {"task_type": task_type, "task_idx": str(task_idx)})
        # 4. 等待界面稳定后获取首屏截图
        await asyncio.sleep(4)
        return await self._fetch_screenshot()

    async def step(self, action: dict) -> str:
        """执行一个动作，返回新截图 base64。"""
        if self.screen_size:
            width, height = self.screen_size
            action = scale_coordinates(dict(action), width, height)
        android = convert_action_to_android(action)
        actions = android if isinstance(android, list) else [android]
        screenshot = ""
        for act in actions:
            await self._post_json("/execute_action", act)
            await asyncio.sleep(1)
            screenshot = await self._fetch_screenshot()
        return screenshot

    async def get_score(self, task_type: str, task_idx: int = 0) -> Optional[float]:
        """获取环境得分（0/1）。"""
        try:
            data = await self._get("/task/score", {"task_type": task_type, "task_idx": task_idx})
            score = data.get("score")
            return float(score) if score is not None else None
        except Exception:
            return None

    async def close_app(self, app_name: str = "") -> None:
        """关闭指定 app。
        
        直连模式下：不关闭环境（由 free_clients 队列控制复用），
        仅尝试关闭 app（忽略失败）。
        """
        if app_name:
            try:
                await self._post("/close_app", {"app_name": app_name})
            except Exception:
                pass


def parse_host_base(host: str) -> str:
    """解析 host 的 scheme://ip 前缀（去掉端口）。"""
    m = re.match(r"^(https?://[^:/]+)(?::\d+)?", host)
    return m.group(1) if m else host.rstrip("/")