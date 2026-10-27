"""用 Windows 内置中文语音生成 OpenVoice 的参考音色样本。

为什么需要它：OpenVoice 音色转换必须有参考音频；为了让仓库自带资源可复现、
不依赖外部下载，这里用本机 SAPI（Microsoft Huihui）生成 6 句中文参考音频，
再重采样到 22050Hz，作为 `resources/ly2.wav`。

用法：python scripts/make_reference.py
"""
from __future__ import annotations

import os
import subprocess
import tempfile

import librosa
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(ROOT, "resources", "ly2.wav")
RAW_PATH = os.path.join(ROOT, "resources", "_ly2_raw.wav")

REFERENCE_TEXT = (
    "早上好，现在为您播报今天的行程。"
    "今天上午九点有高等数学课，教室在教学楼A区三零一。"
    "当前体感温度二十六摄氏度，天气适宜，适合步行前往。"
    "未来两小时没有降水，可以不用带伞。"
    "请提前十分钟出发，祝你今天学习顺利。"
    "一路平安，我们下节课再见。"
)


def synthesize_with_sapi(text: str, out_path: str) -> None:
    """调用 PowerShell + System.Speech 生成 16kHz 单声道 WAV。"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(text)
        text_path = tmp.name
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$s.SelectVoice('Microsoft Huihui Desktop');"
        f"$s.SetOutputToWaveFile('{out_path}');"
        f"$s.Speak([IO.File]::ReadAllText('{text_path}',[Text.Encoding]::UTF8));"
        "$s.Dispose();"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    finally:
        os.unlink(text_path)


def main() -> int:
    synthesize_with_sapi(REFERENCE_TEXT, RAW_PATH)
    audio, _ = librosa.load(RAW_PATH, sr=22050, mono=True)
    # 统一到 OpenVoice 期望的 22050Hz，并做峰值归一化，避免转换时爆音
    peak = float(abs(audio).max()) or 1.0
    audio = audio / peak * 0.9
    sf.write(OUT_PATH, audio, 22050)
    os.remove(RAW_PATH)
    print(f"参考音色已生成：{OUT_PATH}，时长 {len(audio) / 22050:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
