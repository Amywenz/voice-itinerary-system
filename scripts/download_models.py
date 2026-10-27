"""下载 OpenVoice V1 五个权重文件（从 hf-mirror 镜像，适配国内网络）。

规则文件要求 5 个权重路径：
  checkpoints/base_speakers/ZH/config.json
  checkpoints/base_speakers/ZH/checkpoint.pth
  checkpoints/base_speakers/ZH/zh_default_se.pth
  checkpoints/converter/config.json
  checkpoints/converter/checkpoint.pth

用法：python scripts/download_models.py
"""
from __future__ import annotations

import os
import sys
import time
import urllib.request

BASE_URL = "https://hf-mirror.com/myshell-ai/OpenVoice/resolve/main/"
FILES = [
    "checkpoints/base_speakers/ZH/config.json",
    "checkpoints/base_speakers/ZH/checkpoint.pth",
    "checkpoints/base_speakers/ZH/zh_default_se.pth",
    "checkpoints/converter/config.json",
    "checkpoints/converter/checkpoint.pth",
]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def download(rel_path: str, retries: int = 3) -> int:
    """下载单个文件，已存在且大小合理则跳过，返回文件字节数。"""
    target = os.path.join(ROOT, rel_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.exists(target) and os.path.getsize(target) > 100:
        print(f"[skip] {rel_path} ({os.path.getsize(target)} bytes)")
        return os.path.getsize(target)

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(BASE_URL + rel_path, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
            with open(target, "wb") as f:
                f.write(data)
            print(f"[ok]   {rel_path} ({len(data)} bytes)")
            return len(data)
        except Exception as exc:  # 网络异常时重试，最终失败要显式抛出
            print(f"[warn] {rel_path} 第 {attempt} 次失败：{exc}")
            if attempt == retries:
                raise
            time.sleep(2)


def main() -> int:
    print("开始下载 OpenVoice 权重（约 292MB）…")
    total = sum(download(f) for f in FILES)
    print(f"完成，共 {total / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
