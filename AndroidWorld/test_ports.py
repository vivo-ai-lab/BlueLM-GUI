"""测试 5001~5064 所有端口的 reset 相关接口是否正常。

测试接口：
  1. POST /reset?go_home=true
  2. GET /suite/reinitialize?n_task_combinations=1&seed=42&task_family=android_world
  3. POST /task/initialize?task_type=AudioRecorderRecordAudio&task_idx=0

用法：
  python test_ports.py
"""
import asyncio
import base64
import io
import time
import aiohttp
from pathlib import Path
from urllib.parse import urlencode
from PIL import Image

HOST = "http://xx.xx.xx.xx"

PORT_MIN = 5001
PORT_MAX = 5064

TIMEOUT = 10  # 每个接口超时（秒）
CONCURRENCY = 32  # 并发数
SCREENSHOT_DIR = Path("screenshots")

# 测试 task_type（用简单常见的，不依赖特定 app）
TASK_TYPE = "OsmAndTrack"# "SaveCopyOfReceiptTaskEval"# "OsmAndTrack" #"RecipeDeleteMultipleRecipesWithNoise"#"ExpenseAddSingle"


async def save_screenshot(session: aiohttp.ClientSession, base: str, port: int) -> bool:
    """获取模拟器当前截图并保存为 screenshots/{port}.png。"""
    try:
        url = f"{base}/screenshot?wait_to_stabilize=True"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
            if resp.status != 200:
                return False
            data = await resp.json()
            if not isinstance(data, dict):
                return False
            pixels = data.get("pixels") or ""
            if not pixels:
                return False
            if pixels.startswith("data:image"):
                pixels = pixels.split(",", 1)[1]
            img = Image.open(io.BytesIO(base64.b64decode(pixels)))
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            img.save(SCREENSHOT_DIR / f"{port}.png")
            return True
    except Exception:
        return False


async def test_port(session: aiohttp.ClientSession, port: int) -> dict:
    """测试单个端口四个接口，返回 {port, reset, suite, task_init, tear_down, error}。"""
    base = f"{HOST}:{port}"
    result = {"port": port, "reset": "❌", "suite": "❌", "task_init": "❌", "tear_down": "❌", "screenshot": "-"}

    # 1. POST /reset
    try:
        url = f"{base}/reset?{urlencode({'go_home': True})}"
        async with session.post(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
            if resp.status == 200:
                data = await resp.json()
                result["reset"] = "✅" if data.get("status") == "success" else "⚠️"
            else:
                result["reset"] = f"({resp.status})"
    except asyncio.TimeoutError:
        result["reset"] = "⏳"
    except Exception as e:
        result["reset"] = "ERR"

    # 获取并保存截图（仅当 /reset 成功时）
    if result["reset"] == "✅":
        result["screenshot"] = "✅" if await save_screenshot(session, base, port) else "❌"

    # 2. GET /suite/reinitialize
    try:
        params = {"n_task_combinations": "1", "seed": "42", "task_family": "android_world"}
        url = f"{base}/suite/reinitialize?{urlencode(params)}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
            if resp.status == 200:
                data = await resp.json()
                result["suite"] = "✅" if data.get("status") == "success" else "⚠️"
            else:
                result["suite"] = f"({resp.status})"
    except asyncio.TimeoutError:
        result["suite"] = "⏳"
    except Exception as e:
        result["suite"] = "ERR"

    # 3. POST /task/initialize
    try:
        params = {"task_type": TASK_TYPE, "task_idx": "0"}
        url = f"{base}/task/initialize?{urlencode(params)}"
        async with session.post(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
            if resp.status == 200:
                data = await resp.json()
                result["task_init"] = "✅" if data.get("status") == "success" else "⚠️"
            else:
                result["task_init"] = f"({resp.status})"
    except asyncio.TimeoutError:
        result["task_init"] = "⏳"
    except Exception as e:
        result["task_init"] = "ERR"

    # 4. POST /task/tear_down（清理任务）
    try:
        params = {"task_type": TASK_TYPE, "task_idx": "0"}
        url = f"{base}/task/tear_down?{urlencode(params)}"
        async with session.post(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
            if resp.status == 200:
                data = await resp.json()
                result["tear_down"] = "✅" if data.get("status") == "success" else "⚠️"
            else:
                result["tear_down"] = f"({resp.status})"
    except asyncio.TimeoutError:
        result["tear_down"] = "⏳"
    except Exception as e:
        result["tear_down"] = "ERR"

    return result


async def main():
    ports = list(range(PORT_MIN, PORT_MAX + 1))
    print(f"测试 {HOST} 端口 {PORT_MIN}~{PORT_MAX}（共 {len(ports)} 个端口）")
    print(f"并发数: {CONCURRENCY}")
    print(f"测试接口: POST /reset → GET /suite/reinitialize → POST /task/initialize → POST /task/tear_down → GET /screenshot")
    print("-" * 130)
    print(f"{'端口':<8} {'POST /reset':<18} {'GET /suite/reinitialize':<28} {'POST /task/initialize':<26} {'POST /task/tear_down':<24} {'截图':<8} 结果")
    print("-" * 130)

    connector = aiohttp.TCPConnector(limit=CONCURRENCY, limit_per_host=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        sem = asyncio.Semaphore(CONCURRENCY)

        async def _test(port: int) -> dict:
            async with sem:
                return await test_port(session, port)

        tasks = [asyncio.create_task(_test(p)) for p in ports]
        all_ok = True
        for coro in asyncio.as_completed(tasks):
            r = await coro
            reset_ok = r["reset"] == "✅"
            suite_ok = r["suite"] == "✅"
            task_ok = r["task_init"] == "✅"
            tear_ok = r["tear_down"] == "✅"
            shot_ok = r["screenshot"] != "❌"
            total_ok = reset_ok and suite_ok and task_ok and tear_ok and shot_ok
            status = "✅ 全部正常" if total_ok else "❌ 异常"
            print(f"{r['port']:<8} {r['reset']:<18} {r['suite']:<28} {r['task_init']:<26} {r['tear_down']:<24} {r['screenshot']:<8} {status}")
            if not total_ok:
                all_ok = False

        print("-" * 130)
        if all_ok:
            print(f"\n✅ 所有端口 ({PORT_MIN}~{PORT_MAX}) 全部正常，截图已保存至 {SCREENSHOT_DIR}/")
        else:
            print(f"\n❌ 存在异常端口，请检查上表。")

    # 等待所有连接关闭
    await asyncio.sleep(0.5)


if __name__ == "__main__":
    start = time.time()
    asyncio.run(main())
    print(f"耗时: {time.time() - start:.1f}s")
