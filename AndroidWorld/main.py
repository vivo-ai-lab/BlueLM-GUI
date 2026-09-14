"""动态评测主入口。

流程：
  1. 加载配置，通过模拟器接口动态获取评测数据
  2. 连接 vLLM（已由 start_vllm.sh 独立启动）
  3. 根据模拟器端口数量确定并发异步数量
  4. 并发执行所有样本的轨迹评测（每条完成立即落盘）
  5. 汇总结果并落盘

用法：
  python main.py --config config.yaml
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import json
import random
import re
from pathlib import Path
from typing import Any

import yaml

from agent import run_trajectory
from data_client import fetch_eval_samples
from emulator_client import EmulatorClient, parse_host_base
from vllm_client import VLLMClient


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_emulator_url(emu_cfg: dict) -> str:
    """解析模拟器后端地址。

    从 config.yaml 读取 emulator.host，若不含端口则补上 port_min。
    """
    url = emu_cfg.get("host", "")
    if not url:
        url = "http://localhost:8000"
    url = url.rstrip("/")
    # 直连模式：host 无端口，用 port_min 作为 suite 数据接口端口
    if ":" not in url.split("://")[-1]:
        port_min = int(emu_cfg.get("port_min", 5001))
        url = f"{url}:{port_min}"
    return url


def load_samples(data_cfg: dict, emu_cfg: dict) -> list[dict]:
    """通过模拟器接口动态获取评测数据。"""
    samples = fetch_eval_samples(
        base_url=_resolve_emulator_url(emu_cfg),
        seed=int(data_cfg.get("seed", 42)),
        max_index=int(data_cfg.get("max_index", -1)),
        max_retries=int(data_cfg.get("max_retries", 3)),
        timeout=int(data_cfg.get("timeout", 240)),
    )
    max_samples = int(data_cfg.get("max_samples", -1))
    if max_samples > 0 and max_samples < len(samples):
        random.seed(int(data_cfg.get("seed", 42)))
        samples = random.sample(samples, max_samples)
    return samples


def _to_saved_messages(messages: list[dict]) -> list[dict]:
    """将内部消息转换为训练侧 save_pretrained 的 OpenAI 多模态格式。

    内部格式: {"role", "content": str, "images": [b64, ...]}
    训练侧格式: {"role", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
                                     {"type": "text", "text": ...}],
                 "image_percentage": None}
    """
    saved = []
    for m in messages:
        content: list[dict] = []
        for b64 in m.get("images", []):
            url = b64 if b64.startswith("data:image") else f"data:image/jpeg;base64,{b64}"
            content.append({"type": "image_url", "image_url": {"url": url}})
        if m.get("content"):
            content.append({"type": "text", "text": m["content"]})
        saved.append({"role": m["role"], "content": content, "image_percentage": None})
    return saved


def build_emulator_clients(emu_cfg: dict) -> list[EmulatorClient]:
    """根据端口范围构建模拟器客户端列表。

    直连模式：每个端口对应一台独立 AVD 模拟器实例。
    并发异步数量 = min(端口数量, vllm 并发数量)。
    """
    timeout = int(emu_cfg.get("timeout", 240))
    max_retry = int(emu_cfg.get("max_retry", 3))
    port_min = int(emu_cfg.get("port_min", 5001))
    port_max = int(emu_cfg.get("port_max", 5064))
    port_step = int(emu_cfg.get("port_step", 1))
    host = _resolve_emulator_url(emu_cfg)
    base = parse_host_base(host)
    clients = [
        EmulatorClient(f"{base}:{port}", timeout, max_retry)
        for port in range(port_min, port_max + 1, port_step)
    ]
    return clients


async def run_sample(
    client: EmulatorClient,
    generate,
    sample: dict,
    system_prompt: str,
    agent_cfg: dict,
) -> dict:
    """执行单个样本的评测，返回结果 dict。"""
    result = await run_trajectory(
        client=client,
        generate=generate,
        sample=sample,
        system_prompt=system_prompt,
        cfg=agent_cfg,
    )
    return {
        "task_type": sample.get("task_type", ""),
        "package_name": sample.get("package_name", ""),
        "seed": sample.get("seed"),
        "complexity": sample.get("complexity"),
        "instruction": sample["prompt"][0]["content"],
        "success": result.success,
        "score": result.score,
        "turns": result.turns,
        "num_actions": len(result.actions),
        "duration": round(result.duration, 2),
        "error": result.error,
        "device_addr": client.host,  # 记录模拟器地址，便于排查问题
        "actions": result.actions,
        "raw_outputs": result.raw_outputs,
        "messages": _to_saved_messages(result.messages),
        "screenshots": result.screenshots,
    }


async def main(config_path: str) -> None:
    cfg = load_config(config_path)
    model_cfg = cfg["model"]
    sampling_cfg = cfg["sampling"]
    data_cfg = cfg["data"]
    emu_cfg = cfg["emulator"]
    agent_cfg = cfg["agent"]
    out_cfg = cfg["output"]
    concurrency_cfg = cfg.get("concurrency", {})

    # 输出目录：{dir}/{exp_name}/
    exp_name = out_cfg.get("exp_name", "default")
    out_dir = Path(out_cfg["dir"]) / exp_name
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[eval] 输出目录: {out_dir}")

    # 1. 通过模拟器接口动态获取评测数据
    samples = load_samples(data_cfg, emu_cfg)
    if not samples:
        raise RuntimeError("评测数据接口未返回任何样本，请检查模拟器服务可用性")
    print(f"[eval] 获取 {len(samples)} 条评测样本 (seed={data_cfg.get('seed', 42)})")

    # 2. 加载 system prompt
    with open(agent_cfg["system_prompt"], "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # 3. 连接 vLLM（已由 start_vllm.sh 独立启动）
    print(f"[eval] 连接 vLLM API: {model_cfg['api_url']}")
    vllm = VLLMClient(
        base_url=model_cfg["api_url"],
        model=model_cfg.get("name", ""),
        max_tokens=int(sampling_cfg.get("max_tokens", 2048)),
        temperature=float(sampling_cfg.get("temperature", 0.0)),
        top_p=float(sampling_cfg.get("top_p", 1.0)),
        top_k=int(sampling_cfg.get("top_k", -1)),
        timeout=float(model_cfg.get("timeout", 300)),
        skip_special_tokens=bool(sampling_cfg.get("skip_special_tokens", False)),
        enable_thinking=sampling_cfg.get("enable_thinking"),
    )
    # 健康检查：确认 vLLM 服务可用
    import httpx
    health_url = model_cfg["api_url"].rstrip("/").replace("/v1", "") + "/health"
    try:
        resp = httpx.get(health_url, timeout=10)
        resp.raise_for_status()
        print("[eval] vLLM 服务健康检查通过")
    except Exception as e:
        print(f"[eval] 警告: vLLM 服务健康检查失败: {e}（请确认 start_vllm.sh 已启动）")
        raise

    # 4. 构建模拟器客户端（端口数 = 可用 AVD 数量）
    clients = build_emulator_clients(emu_cfg)
    n_ports = len(clients)
    # 5. 并发评测：vLLM 并发与模拟器并发分别控制
    vllm_concurrency = int(concurrency_cfg.get("vllm", 16))
    print(f"[eval] vLLM 并发请求数 = {vllm_concurrency}")

    # 模拟器并发 = min(端口数量, vLLM 并发数量)
    emulator_concurrency = min(n_ports, vllm_concurrency)
    # 允许配置强制限制模拟器并发（-1 表示自动决定）
    cfg_emu_conc = int(concurrency_cfg.get("emulator", -1))
    if cfg_emu_conc > 0:
        emulator_concurrency = min(emulator_concurrency, cfg_emu_conc)
    print(f"[eval] 端口数 = {n_ports}，模拟器并发 = {emulator_concurrency}")

    emu_semaphore = asyncio.Semaphore(emulator_concurrency)
    vllm_semaphore = asyncio.Semaphore(vllm_concurrency)
    results: list[dict] = []

    # 轨迹目录提前创建，供每条轨迹完成后立即落盘
    traj_dir = out_dir / "trajectories"
    traj_dir.mkdir(exist_ok=True)

    def _safe_name(name: str) -> str:
        """清洗为安全文件名片段（去路径分隔符/控制字符）。"""
        cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name).strip().strip(".")
        return cleaned or "unknown"

    # 空闲 client 队列：保证同一 client 同一时刻只被一个任务使用，
    # 避免并发任务同时操作同一台模拟器导致冲突
    free_clients = asyncio.Queue()
    for c in clients:
        free_clients.put_nowait(c)

    async def _run_with_slot(sample: dict, idx: int) -> dict:
        # 同时占用模拟器与 vLLM 配额
        async with emu_semaphore, vllm_semaphore:
            client = await free_clients.get()
            released = False  # 标记是否已在重试路径中归还 client
            try:
                res = await run_sample(
                    client=client,
                    generate=vllm.generate,
                    sample=sample,
                    system_prompt=system_prompt,
                    agent_cfg=agent_cfg,
                )
                # 模拟器会话异常（reset/step 失败）：换一个 client 重试一次
                if not res.get("success") and res.get("error") and (
                    "reset" in res["error"] or "step" in res["error"]
                ):
                    free_clients.put_nowait(client)  # 归还当前 client
                    released = True
                    try:
                        client = await asyncio.wait_for(free_clients.get(), timeout=10)
                        released = False  # 成功获取新 client，重置标记
                    except asyncio.TimeoutError:
                        pass  # 无空闲 client，保留原结果（client 已归还，不再重复 put）
                    else:
                        res = await run_sample(
                            client=client,
                            generate=vllm.generate,
                            sample=sample,
                            system_prompt=system_prompt,
                            agent_cfg=agent_cfg,
                        )
            finally:
                if not released:
                    free_clients.put_nowait(client)
        # 立即保存该条轨迹（不等全部评测完成）
        # 命名：{task_type}.json；截图存到同名文件夹 {task_type}/
        # 同一 task_type 有多个样本时加序号后缀避免覆盖
        task_type = _safe_name(str(res.get("task_type", "unknown")))
        base_name = task_type
        # 若该 task_type 已保存过（同名文件已存在），加序号后缀
        json_path = traj_dir / f"{base_name}.json"
        if json_path.exists():
            n = 1
            while (traj_dir / f"{base_name}_{n}.json").exists():
                n += 1
            base_name = f"{base_name}_{n}"
            json_path = traj_dir / f"{base_name}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        # 保存截图到同名文件夹；把对应 action 可视化（文字描述 + 点击类动作画圈标注）
        shot_dir = traj_dir / base_name
        shot_dir.mkdir(exist_ok=True)
        from io import BytesIO

        from PIL import Image, ImageDraw, ImageFont

        # 模型输出的坐标是 0~1000 相对坐标，可视化时按截图实际宽高转换
        coord_scale = 1000.0
        actions = res.get("actions", [])
        for si, b64 in enumerate(res.get("screenshots", [])):
            try:
                img_bytes = base64.b64decode(b64)
            except Exception:
                continue
            # screenshot_i 上标注基于该截图执行的动作 actions[si]
            if si < len(actions):
                act = actions[si]
                if isinstance(act, dict):
                    try:
                        img = Image.open(BytesIO(img_bytes)).convert("RGB")
                        draw = ImageDraw.Draw(img)
                        w, h = img.size
                        act_name = act.get("action", "")
                        parts = []
                        # 点击类动作：画圈 + 标注像素坐标
                        coord = act.get("coordinate")
                        if coord and len(coord) == 2 and coord[0] is not None and coord[1] is not None:
                            cx = round(coord[0] * w / coord_scale)
                            cy = round(coord[1] * h / coord_scale)
                            parts.append(f"({cx}, {cy})")
                            if act_name in ("click", "double_click", "long_press"):
                                r = 30
                                draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline="red", width=5)
                        # swipe/drag：标注起点和终点
                        start = act.get("start_coordinate")
                        end = act.get("end_coordinate")
                        if start and len(start) == 2 and all(v is not None for v in start):
                            sx = round(start[0] * w / coord_scale)
                            sy = round(start[1] * h / coord_scale)
                            parts.append(f"({sx}, {sy})")
                        if isinstance(end, (list, tuple)) and len(end) == 2 and all(v is not None for v in end):
                            ex = round(end[0] * w / coord_scale)
                            ey = round(end[1] * h / coord_scale)
                            parts.append(f"-> ({ex}, {ey})")
                        text = act.get("text")
                        if text is not None:
                            parts.append(f'"{text}"')
                        desc = f"{act_name}: " + " ".join(parts) if parts else act_name
                        # 顶部黑色背景条 + 白色文字
                        try:
                            font = ImageFont.truetype(
                                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44
                            )
                        except Exception:
                            font = ImageFont.load_default()
                        text_bbox = draw.textbbox((0, 0), desc, font=font)
                        tw = text_bbox[2] - text_bbox[0]
                        th = text_bbox[3] - text_bbox[1]
                        draw.rectangle([0, 0, tw + 12, th + 8], fill="black")
                        draw.text((6, 4), desc, fill="white", font=font)
                        buf = BytesIO()
                        img.save(buf, format="PNG")
                        img_bytes = buf.getvalue()
                    except Exception:
                        pass
            with open(shot_dir / f"screenshot_{si:03d}.png", "wb") as f:
                f.write(img_bytes)
        return res

    # 动态分配：空闲 client 队列保证同一模拟器不被并发使用
    tasks = []
    for i, sample in enumerate(samples):
        tasks.append(asyncio.create_task(_run_with_slot(sample, i)))

    # 进度打印
    done_count = 0
    for coro in asyncio.as_completed(tasks):
        try:
            res = await coro
            results.append(res)
        except Exception as e:
            results.append({"error": str(e), "success": False})
        done_count += 1
        if done_count % 10 == 0 or done_count == len(tasks):
            print(f"[eval] 进度: {done_count}/{len(tasks)}")

    # 6. 汇总落盘
    success_count = sum(1 for r in results if r.get("success"))
    avg_score = sum(r.get("score", 0) for r in results) / len(results) if results else 0
    avg_turns = sum(r.get("turns", 0) for r in results) / len(results) if results else 0

    summary = {
        "total": len(results),
        "success": success_count,
        "success_rate": round(success_count / len(results), 4) if results else 0,
        "avg_score": round(avg_score, 4),
        "avg_turns": round(avg_turns, 2),
        "config": cfg,
    }
    summary_path = out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # CSV 汇总
    csv_path = out_dir / "results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "task_type", "package_name", "seed", "instruction",
            "success", "score", "turns", "num_actions", "duration", "error",
        ])
        writer.writeheader()
        for r in results:
            writer.writerow({k: r.get(k) for k in [
                "task_type", "package_name", "seed", "instruction",
                "success", "score", "turns", "num_actions", "duration", "error",
            ]})

    print(f"\n[eval] 完成: {success_count}/{len(results)} 成功, 成功率={summary['success_rate']:.2%}")
    print(f"[eval] 结果已保存到 {out_dir}")

    # 7. 关闭 vLLM
    await vllm.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="动态评测")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    args = parser.parse_args()
    asyncio.run(main(args.config))