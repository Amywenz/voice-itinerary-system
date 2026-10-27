"""从 hf-mirror 下载 Piper 离线音色模型到 voices/。

用法：
    .venv\\Scripts\\python.exe scripts/download_voices.py            # 下载缺失模型
    .venv\\Scripts\\python.exe scripts/download_voices.py --list      # 只打印清单

为什么要单独下载：piper 权重每个约 60-77MB，不进版本库，与 checkpoints/ 一样
由脚本按需拉取；下载完 .onnx 与同名 .onnx.json 才算完整。
"""
from __future__ import annotations

import argparse
import os
import sys

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE_DIR = os.path.join(BASE_DIR, "voices")
MIRROR = "https://hf-mirror.com/rhasspy/piper-voices/resolve/main"

# key = 模型文件名（不含扩展名），value = 仓库内相对路径
MODELS = {
    "zh_CN-huayan-medium": "zh/zh_CN/huayan/medium",
    "en_US-lessac-medium": "en/en_US/lessac/medium",
    "en_US-ryan-medium": "en/en_US/ryan/medium",
    "es_ES-davefx-medium": "es/es_ES/davefx/medium",
    "es_ES-sharvard-medium": "es/es_ES/sharvard/medium",
}


def target_paths(name: str) -> tuple[str, str]:
    return (
        os.path.join(VOICE_DIR, f"{name}.onnx"),
        os.path.join(VOICE_DIR, f"{name}.onnx.json"),
    )


def is_ready(name: str) -> bool:
    onnx, config = target_paths(name)
    return os.path.exists(onnx) and os.path.exists(config)


def download(url: str, path: str, retries: int = 3) -> None:
    """流式下载，失败重试；先写 .part 再改名，避免半截文件被当成可用模型。"""
    tmp = path + ".part"
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        if not chunk:
                            continue
                        f.write(chunk)
                        done += len(chunk)
                os.replace(tmp, path)
                print(f"  完成 {os.path.basename(path)} · {done / 1024 / 1024:.1f}MB"
                      + (f" / {total / 1024 / 1024:.1f}MB" if total else ""))
                return
        except Exception as exc:  # 网络抖动很常见，重试即可
            print(f"  第 {attempt} 次失败：{exc}")
            if os.path.exists(tmp):
                os.unlink(tmp)
            if attempt == retries:
                raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下载 Piper 离线音色")
    parser.add_argument("--list", action="store_true", help="只列出模型与状态")
    args = parser.parse_args(argv)

    os.makedirs(VOICE_DIR, exist_ok=True)
    if args.list:
        for name in MODELS:
            print(f"{'OK ' if is_ready(name) else 'MISS'} {name}")
        return 0

    for name, remote in MODELS.items():
        if is_ready(name):
            print(f"[跳过] {name} 已存在")
            continue
        print(f"[下载] {name}")
        for ext in (".onnx", ".onnx.json"):
            download(f"{MIRROR}/{remote}/{name}{ext}",
                     os.path.join(VOICE_DIR, f"{name}{ext}"))

    missing = [n for n in MODELS if not is_ready(n)]
    if missing:
        print("仍有缺失：" + ", ".join(missing))
        return 1
    print(f"全部就绪，目录：{VOICE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
