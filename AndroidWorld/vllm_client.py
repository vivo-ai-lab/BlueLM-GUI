from __future__ import annotations

import base64
import io
import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Optional

import httpx
from openai import AsyncOpenAI
from PIL import Image


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

RESIZE_FACTOR = 32
IMAGE_MIN_TOKEN_NUM = 4
IMAGE_MAX_TOKEN_NUM = 900
MIN_PIXELS = IMAGE_MIN_TOKEN_NUM * RESIZE_FACTOR ** 2
MAX_PIXELS = IMAGE_MAX_TOKEN_NUM * RESIZE_FACTOR ** 2
MAX_RATIO = 200


def _round_by_factor(number: int, factor: int) -> int:
    return round(number / factor) * factor


def _floor_by_factor(number: int, factor: int) -> int:
    return math.floor(number / factor) * factor


def _ceil_by_factor(number: int, factor: int) -> int:
    return math.ceil(number / factor) * factor


def _smart_resize(height: int, width: int, factor: int, min_pixels: int, max_pixels: int) -> tuple[int, int]:
    if max(height, width) / min(height, width) > MAX_RATIO:
        raise ValueError(
            f"absolute aspect ratio must be smaller than {MAX_RATIO}, "
            f"got {max(height, width) / min(height, width)}"
        )
    h_bar = max(factor, _round_by_factor(height, factor))
    w_bar = max(factor, _round_by_factor(width, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = _floor_by_factor(height / beta, factor)
        w_bar = _floor_by_factor(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = _ceil_by_factor(height * beta, factor)
        w_bar = _ceil_by_factor(width * beta, factor)
    return h_bar, w_bar


def _to_rgb(pil_image: Image.Image) -> Image.Image:
    if pil_image.mode == "RGBA":
        white_background = Image.new("RGB", pil_image.size, (255, 255, 255))
        white_background.paste(pil_image, mask=pil_image.split()[3])
        return white_background
    return pil_image.convert("RGB")


def _resize_image_like_training(b64: str) -> str:
    raw = base64.b64decode(b64)
    img = Image.open(io.BytesIO(raw))
    img = _to_rgb(img)
    width, height = img.size
    resized_height, resized_width = _smart_resize(
        height, width, factor=RESIZE_FACTOR, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS,
    )
    img = img.resize((resized_width, resized_height))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


class VLLMClient:

    def __init__(
        self,
        base_url: str = "http://localhost:8001/v1",
        model: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.0,
        top_p: float = 1.0,
        top_k: int = -1,
        timeout: float = 300.0,
        skip_special_tokens: bool = False,
        enable_thinking: Optional[bool] = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.skip_special_tokens = skip_special_tokens
        self.enable_thinking = enable_thinking
        self._client = AsyncOpenAI(
            api_key="EMPTY",
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=30.0),
        )

    async def generate(self, messages: list[dict]) -> str:
        openai_messages = []
        for msg in messages:
            m = dict(msg)
            imgs = m.pop("images", None)
            if imgs:
                content: list[dict] = []
                for b64 in imgs:
                    resized_b64 = _resize_image_like_training(b64)
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": _to_data_uri(resized_b64), "detail": "high"},
                    })
                if m.get("content"):
                    content.append({"type": "text", "text": m["content"]})
                m["content"] = content
            openai_messages.append(m)

        log_messages = []
        for msg in openai_messages:
            m = dict(msg)
            content = m.get("content", "")
            if isinstance(content, list):
                parts = []
                for c in content:
                    if c.get("type") == "image_url":
                        parts.append({"type": "image_url", "image_url": "default_image"})
                    else:
                        parts.append(c)
                m["content"] = parts
            log_messages.append(m)
        logger.info(f"conversation_messages_record: {json.dumps(log_messages, ensure_ascii=False)}")

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }

        extra_body: dict[str, Any] = {
            "skip_special_tokens": self.skip_special_tokens,
        }
        if self.top_k is not None and self.top_k > 0:
            extra_body["top_k"] = self.top_k
        if self.enable_thinking is not None:
            extra_body["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}
        kwargs["extra_body"] = extra_body

        resp = await self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    async def close(self) -> None:
        await self._client.close()


def _to_data_uri(b64: str) -> str:
    if b64.startswith("data:image"):
        return b64
    try:
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        fmt = (img.format or "PNG").lower()
        mime = "image/jpeg" if fmt == "jpeg" else f"image/{fmt}"
    except Exception:
        mime = "image/png"
    return f"data:{mime};base64,{b64}"