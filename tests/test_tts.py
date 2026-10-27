"""语音合成与播放测试：权重清单、空文本、降级链路、缺失文件。"""
from __future__ import annotations

import os
import sys

import pytest

import play
import tts as tts_module


def test_five_weight_files_declared():
    """C-2：5 个权重路径与评分细则逐项一致。"""
    assert len(tts_module.WEIGHT_FILES) == 5
    assert "checkpoints/base_speakers/ZH/config.json" in tts_module.WEIGHT_FILES
    assert "checkpoints/base_speakers/ZH/checkpoint.pth" in tts_module.WEIGHT_FILES
    assert "checkpoints/base_speakers/ZH/zh_default_se.pth" in tts_module.WEIGHT_FILES
    assert "checkpoints/converter/config.json" in tts_module.WEIGHT_FILES
    assert "checkpoints/converter/checkpoint.pth" in tts_module.WEIGHT_FILES


def test_check_weights_reports_missing(monkeypatch):
    monkeypatch.setattr(os.path, "exists", lambda path: False)
    status = tts_module.check_weights()
    assert status["available"] is False
    assert len(status["missing"]) == 5


def test_empty_text_raises():
    """异常：空文本必须显式报错，不能生成无声 wav。"""
    with pytest.raises(ValueError):
        tts_module.tts({}, text="   ")


def test_missing_weather_txt_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        tts_module.tts({"paths": {"weather_text": str(tmp_path / "absent.txt")}})


@pytest.mark.skipif(sys.platform != "win32", reason="SAPI 仅支持 Windows")
def test_sapi_fallback_generates_22050_wav(tmp_path, monkeypatch):
    """C-6：OpenVoice 不可用时自动降级 SAPI，输出 22050Hz 的 wav 并标注原因。"""
    def boom(text, config):
        raise RuntimeError("模拟权重缺失")

    monkeypatch.setattr(tts_module, "_openvoice_tts", boom)
    # 指标文件也写到临时目录，避免测试覆盖交付用的 outputs/tts_meta.json
    monkeypatch.setattr(tts_module, "META_PATH", str(tmp_path / "tts_meta.json"))
    config = {
        "tmp_audio": str(tmp_path / "tmp.wav"),
        "audio_dir": str(tmp_path / "advice.wav"),
        "tts_engine": "auto",
        "speed": 1.0,
    }
    meta = tts_module.tts(config, text="测试语音合成链路。")

    assert meta["engine"] == "sapi"
    assert meta["sample_rate"] == 22050
    assert os.path.getsize(meta["save_path"]) > 1000
    assert "模拟权重缺失" in meta["fallback_reason"]
    assert os.path.exists(meta["tmp_path"])


def test_play_missing_file_raises(tmp_path):
    """C-7：播放不吞异常，缺失文件必须抛出 FileNotFoundError。"""
    with pytest.raises(FileNotFoundError):
        play.play_audio(str(tmp_path / "absent.wav"))
