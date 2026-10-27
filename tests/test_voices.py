"""语言注册表、音色可用性与云 TTS 降级测试。"""
from __future__ import annotations

import os

import soundfile as sf

import voices


def _fake_write(text, model, out_path, speed):
    """替代真实 Piper 推理：写 0.2 秒静音，保证 meta 能读到采样率。"""
    sf.write(out_path, [0.0] * 4410, 22050)


def test_catalog_covers_required_languages():
    data = voices.catalog()
    codes = {row["code"] for row in data["languages"]}
    assert {"zh-CN", "en-US", "es-ES", "yue"} <= codes
    for row in data["languages"]:
        assert row["voices"], f"{row['code']} 缺少音色"
        assert all(voice["lang"] == row["code"] for voice in row["voices"])


def test_voice_ids_are_unique_and_lookup_works():
    ids = [voice["id"] for voice in voices.VOICES]
    assert len(ids) == len(set(ids))
    assert voices.get_voice("es-dave")["engine"] == "piper"
    assert voices.get_voice("yue-cloud")["lang"] == "yue"


def test_default_voice_per_language_is_member():
    for code in voices.LANGUAGES:
        voice_id = voices.default_voice(code)
        assert voices.get_voice(voice_id)["lang"] == code


def test_missing_piper_model_marks_unavailable(monkeypatch):
    monkeypatch.setattr(voices, "piper_ready", lambda model: False)
    voice = voices.get_voice("es-dave")
    ok, reason = voices.voice_available(voice)
    assert ok is False
    assert "模型未下载" in reason


def test_cloud_voice_reports_config_requirement(monkeypatch):
    monkeypatch.setattr(voices, "cloud_ready", lambda: False)
    ok, reason = voices.voice_available(voices.get_voice("yue-cloud"))
    assert ok is False
    assert "cloud_tts" in reason


def test_synthesize_rejects_unknown_language():
    try:
        voices.synthesize("你好", lang="xx-YY")
    except ValueError as exc:
        assert "不支持的语言" in str(exc)
    else:  # pragma: no cover - 没有抛异常就是失败
        raise AssertionError("未知语言应当抛 ValueError")


def test_synthesize_rejects_mismatched_voice():
    try:
        voices.synthesize("hello", lang="en-US", voice_id="zh-huayan")
    except ValueError as exc:
        assert "不属于语言" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("音色与语言不匹配应当抛 ValueError")


def test_piper_synthesis_returns_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(voices, "_piper_tts", _fake_write)
    monkeypatch.setattr(voices, "CACHE_PATH", str(tmp_path / "voice_meta.json"))
    out = tmp_path / "voice_zh.wav"

    meta = voices.synthesize("你好，世界", "zh-CN", "zh-huayan", out_path=str(out))
    assert meta["engine"] == "piper"
    assert meta["sample_rate"] == 22050
    assert meta["fallback_reason"] == ""
    assert os.path.exists(out)
    assert os.path.exists(tmp_path / "voice_meta.json")


def test_cloud_unconfigured_falls_back_to_mandarin(tmp_path, monkeypatch):
    """云 TTS 未配置：明确降级为普通话音色，并写清原因。"""
    monkeypatch.setattr(voices, "cloud_ready", lambda: False)
    monkeypatch.setattr(voices, "_piper_tts", _fake_write)
    monkeypatch.setattr(voices, "CACHE_PATH", str(tmp_path / "voice_meta.json"))
    out = tmp_path / "voice_yue.wav"

    meta = voices.synthesize("早晨，記得帶遮。", "yue", "yue-cloud",
                             out_path=str(out), allow_fallback=True)
    assert meta["engine"] == "piper"
    assert meta["voice_id"] == "zh-huayan"
    assert "云 TTS" in meta["fallback_reason"] or "不可用" in meta["fallback_reason"]


def test_cloud_unconfigured_raises_when_fallback_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(voices, "cloud_ready", lambda: False)
    out = tmp_path / "voice_yue.wav"
    try:
        voices.synthesize("早晨", "yue", "yue-cloud", out_path=str(out), allow_fallback=False)
    except RuntimeError as exc:
        assert "云 TTS" in str(exc) or "不可用" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("关闭降级时应抛 RuntimeError")


def test_audio_url_points_to_outputs():
    url = voices.audio_url({"out_path": "outputs/voice_en-ryan.wav",
                            "timestamp": "2026-10-23T15:00:00"})
    assert url.startswith("/outputs/voice_en-ryan.wav?v=")


def test_styles_cover_requested_roles():
    """角色预设：萝莉音/大叔音/机械音/播音腔男女齐备，未知风格回退自然。"""
    ids = {row["id"] for row in voices.catalog()["styles"]}
    assert {"natural", "anchor_f", "anchor_m", "loli", "uncle", "robot"} <= ids
    assert voices.get_style("unknown")["id"] == "natural"
    assert voices.get_style("loli")["pitch"] > 0


def test_broadcast_text_switches_language():
    """换语言时播报文案跟着换，天气词也翻译，不拿外语音色硬读中文。"""
    en = voices.broadcast_text("en-US", "Calculus", 12, "26", "多云", city_key="beijing")
    assert "Calculus" in en and "cloudy" in en and "Beijing" in en
    zh = voices.broadcast_text("zh-CN", "高等数学", 12, "26", "多云", advice="中文完整建议")
    assert zh == "中文完整建议"


def test_farewell_is_stable_within_a_day_and_rotates():
    """告别语同一天固定一条（重复播报不跳），跨天自动轮换。"""
    from datetime import date

    day = date(2026, 10, 23)
    first = voices.farewell("zh-CN", on=day)
    assert first == voices.farewell("zh-CN", on=day)
    assert first in voices.FAREWELLS["zh-CN"]
    picks = {voices.farewell("zh-CN", on=date.fromordinal(day.toordinal() + i)) for i in range(7)}
    assert len(picks) > 1


def test_broadcast_text_ends_with_farewell():
    """外语播报模板也要在结尾补一句该语言的告别语。"""
    text = voices.broadcast_text("en-US", "Calculus", 12, "26", "多云", city_key="beijing")
    assert text.endswith(voices.farewell("en-US"))


def test_foreign_broadcast_is_as_long_as_chinese():
    """外语播报补齐时间/倒计时/体感/降水/资讯，句量和中文一致，不能只播一句。"""
    import weather

    data = weather.get_mock_weather("shanghai")
    common = {"city_name": "上海", "city_key": "shanghai", "weather_data": data}
    en = voices.broadcast_text("en-US", "理工应用英语", 485, 24, "阴", **common)
    es = voices.broadcast_text("es-ES", "理工应用英语", 485, 24, "阴", **common)
    yue = voices.broadcast_text("yue", "理工应用英语", 485, 24, "阴", **common)

    assert "8 hours and 5 minutes" in en and "umbrella" in en
    assert "your next class" in en and "理工" not in en     # 中文课程名不塞给英西音色
    assert "8 horas y 5 minutos" in es and "paraguas" in es
    assert "8小時5分鐘" in yue and "遮" in yue
    assert len(en.split()) >= 60 and len(es.split()) >= 60
