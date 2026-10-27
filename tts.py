"""语音合成模块：OpenVoice 两级流程（基础语音 → 音色转换）。

严格保持评分细则 C-3 的顺序：
  1. BaseSpeakerTTS.tts(text, tmp.wav, ...)      生成平均音色基础语音
  2. ToneColorConverter.convert(tmp.wav, ...)    转换为目标音色 advice.wav

OpenVoice 权重缺失或推理失败时，按 config.tts_engine=auto 降级到 Windows SAPI，
并在 outputs/tts_meta.json 与界面中显式标注 engine=sapi，绝不冒充模型输出。
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime

import librosa
import soundfile as sf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
META_PATH = os.path.join(OUTPUT_DIR, "tts_meta.json")
WEIGHT_FILES = [
    "checkpoints/base_speakers/ZH/config.json",
    "checkpoints/base_speakers/ZH/checkpoint.pth",
    "checkpoints/base_speakers/ZH/zh_default_se.pth",
    "checkpoints/converter/config.json",
    "checkpoints/converter/checkpoint.pth",
]

# 模型只加载一次，避免每次播报都重新读 292MB 权重
_MODEL_CACHE: dict = {}


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


def check_weights(config: dict | None = None) -> dict:
    """检查 5 个权重文件是否存在，返回可用性与缺失清单。"""
    missing = [p for p in WEIGHT_FILES if not os.path.exists(_abs(p))]
    return {
        "available": not missing,
        "missing": missing,
        "files": WEIGHT_FILES,
        "python": "3.11",
    }


def _load_models(config: dict):
    """加载 BaseSpeakerTTS / ToneColorConverter / 源音色与目标音色。"""
    import torch
    from openvoice.api import BaseSpeakerTTS, ToneColorConverter

    ckpt_base = _abs(config.get("ckpt_base", "checkpoints/base_speakers/ZH"))
    ckpt_converter = _abs(config.get("ckpt_converter", "checkpoints/converter"))
    reference = _abs(config.get("reference_speaker", "resources/ly2.wav"))

    cache_key = (ckpt_base, ckpt_converter, reference)
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    status = check_weights()
    if not status["available"]:
        raise FileNotFoundError(
            "OpenVoice 权重缺失：" + ", ".join(status["missing"]) +
            "；请先运行 python scripts/download_models.py"
        )
    if not os.path.exists(reference):
        raise FileNotFoundError(f"参考音频不存在：{reference}")

    # device 按 cuda.is_available() 自选（评分细则 C-2）
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"[OpenVoice] device={device}，加载基础语音合成模型…")
    base_speaker_tts = BaseSpeakerTTS(f"{ckpt_base}/config.json", device=device)
    base_speaker_tts.load_ckpt(f"{ckpt_base}/checkpoint.pth")

    print("[OpenVoice] 加载音色转换器…")
    tone_color_converter = ToneColorConverter(
        f"{ckpt_converter}/config.json",
        device=device,
        enable_watermark=bool(config.get("enable_watermark", False)),
    )
    tone_color_converter.load_ckpt(f"{ckpt_converter}/checkpoint.pth")

    # 源音色：基础说话人的平均音色（官方提供的 zh_default_se.pth）
    source_se = torch.load(f"{ckpt_base}/zh_default_se.pth", map_location=device)

    # 目标音色：参考音频切 3 段，逐段提取后取平均（规避 whisper 依赖）
    target_se, segment_paths = _extract_target_se(
        tone_color_converter, reference, segment_count=3
    )

    models = {
        "device": device,
        "base_tts": base_speaker_tts,
        "converter": tone_color_converter,
        "source_se": source_se,
        "target_se": target_se,
        "segments": segment_paths,
        "reference": reference,
    }
    _MODEL_CACHE[cache_key] = models
    return models


def _extract_target_se(converter, reference_path: str, segment_count: int = 3):
    """把参考音频切成 3 段，提取音色向量并取平均。

    OpenVoice 官方 se_extractor 依赖 whisper 做 VAD；本项目改为等长切段，
    输入明确（3 段参考音频），无需联网下载 whisper 模型。
    """
    import numpy as np

    audio, _ = librosa.load(reference_path, sr=22050, mono=True)
    if len(audio) < 22050:  # 不足 1 秒时无法切段
        parts = [audio]
    else:
        parts = np.array_split(audio, segment_count)

    os.makedirs(os.path.join(OUTPUT_DIR, "segments"), exist_ok=True)
    paths = []
    for index, part in enumerate(parts, start=1):
        path = os.path.join(OUTPUT_DIR, "segments", f"ref_seg_{index}.wav")
        sf.write(path, part, 22050)
        paths.append(path)

    target_se = converter.extract_se(paths)
    return target_se, paths


def _openvoice_tts(text: str, config: dict) -> dict:
    """两级流程：tts() 产 tmp.wav，convert() 产 advice.wav。"""
    models = _load_models(config)
    tmp_path = _abs(config.get("tmp_audio", "outputs/tmp.wav"))
    save_path = _abs(config.get("audio_dir", "outputs/advice.wav"))
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # 第一级：基础语音合成（平均音色）
    models["base_tts"].tts(
        text,
        tmp_path,
        speaker=config.get("speaker", "default"),
        language=config.get("language", "Chinese"),
        speed=float(config.get("speed", 1.0)),
    )

    # 第二级：音色转换（目标音色）
    models["converter"].convert(
        audio_src_path=tmp_path,
        src_se=models["source_se"],
        tgt_se=models["target_se"],
        output_path=save_path,
        message="@WeatherTTS",
    )
    return _build_meta("openvoice", models["device"], tmp_path, save_path,
                       len(models["segments"]), models["reference"])


def _sapi_tts(text: str, config: dict, reason: str = "") -> dict:
    """Windows SAPI 保底合成：先写 tmp.wav，再重采样成 advice.wav。"""
    tmp_path = _abs(config.get("tmp_audio", "outputs/tmp.wav"))
    save_path = _abs(config.get("audio_dir", "outputs/advice.wav"))
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(text)
        text_path = tmp.name

    rate = max(-10, min(10, int((float(config.get("speed", 1.0)) - 1.0) * 10)))
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "try{$s.SelectVoice('Microsoft Huihui Desktop')}catch{};"
        f"$s.Rate={rate};"
        f"$s.SetOutputToWaveFile('{tmp_path}');"
        f"$s.Speak([IO.File]::ReadAllText('{text_path}',[Text.Encoding]::UTF8));"
        "$s.Dispose();"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    finally:
        os.unlink(text_path)

    # 统一到 22050Hz，保证技术指标与 OpenVoice 输出一致
    audio, _ = librosa.load(tmp_path, sr=22050, mono=True)
    peak = float(abs(audio).max()) or 1.0
    sf.write(save_path, audio / peak * 0.9, 22050)
    return _build_meta("sapi", "windows-sapi", tmp_path, save_path, 0,
                       config.get("reference_speaker", ""), reason=reason)


def _build_meta(engine: str, device: str, tmp_path: str, save_path: str,
                segments: int, reference: str, reason: str = "") -> dict:
    info = sf.info(save_path)
    meta = {
        "engine": engine,
        "device": device,
        "tmp_path": tmp_path,
        "save_path": save_path,
        "sample_rate": info.samplerate,
        "duration": round(info.frames / info.samplerate, 2),
        "size_kb": round(os.path.getsize(save_path) / 1024, 1),
        "reference_segments": segments,
        "reference": reference,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "fallback_reason": reason,
    }
    os.makedirs(os.path.dirname(META_PATH), exist_ok=True)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


def tts(config: dict | None = None, text: str | None = None,
        engine: str | None = None) -> dict:
    """把文本合成为 advice.wav，返回技术指标。

    参数：
        config: 已加载的配置字典；缺省时读取 config.yaml
        text:   待合成文本；缺省时读取 resources/weather.txt
        engine: openvoice / sapi / auto；缺省读 config.tts_engine
    """
    if config is None:
        from weather import load_config
        config = load_config()

    if text is None:
        weather_text_path = _abs((config.get("paths") or {}).get(
            "weather_text", "resources/weather.txt"))
        if not os.path.exists(weather_text_path):
            raise FileNotFoundError(
                f"weather.txt 不存在：{weather_text_path}；请先运行 python weather.py --advice-only")
        with open(weather_text_path, "r", encoding="utf-8") as f:
            text = f.read().strip()
    else:
        text = text.strip()
    if not text:
        raise ValueError("待合成文本为空：weather.txt 没有内容，无法生成语音")

    engine = (engine or config.get("tts_engine", "auto")).lower()
    if engine not in ("auto", "openvoice", "sapi"):
        raise ValueError(f"不支持的引擎：{engine}")

    if engine in ("auto", "openvoice"):
        try:
            return _openvoice_tts(text, config)
        except Exception as exc:  # 明确记录降级原因，engine=openvoice 时继续抛出
            if engine == "openvoice":
                raise
            print(f"[警告] OpenVoice 不可用，降级为 Windows SAPI：{exc}")
            return _sapi_tts(text, config, reason=str(exc))

    return _sapi_tts(text, config, reason="配置指定 sapi")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="OpenVoice 两级语音合成")
    parser.add_argument("--text", default=None, help="待合成文本；缺省读 weather.txt")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--engine", default=None, choices=["auto", "openvoice", "sapi"])
    parser.add_argument("--status", action="store_true", help="只检查权重与环境")
    args = parser.parse_args(argv)

    if args.status:
        status = check_weights()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    from weather import load_config
    config = load_config(args.config)
    meta = tts(config, text=args.text, engine=args.engine)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
