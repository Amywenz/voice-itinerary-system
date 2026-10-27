"""全链路测试：mock 数据 → 建议文本 → 运行日志；断网降级。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import yaml

import weather


def write_config(tmp_path, **overrides) -> str:
    config = {
        "api_key": "YOUR_QWEATHER_KEY",
        "provider": "mock",
        "default_city": "dalian",
        "cities": {"dalian": {"city": "101070201", "location": "121.52,38.88"}},
        "reminder_minutes": 10,
        "paths": {"runs": str(tmp_path / "runs.jsonl"),
                  "weather_text": str(tmp_path / "weather.txt")},
    }
    config.update(overrides)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return str(path)


def test_gene_advice_without_tts(tmp_path):
    """FR-05：speak=False 时仍完成 配置→天气→建议→weather.txt→日志。"""
    config_path = write_config(tmp_path)
    result = weather.gene_advice(
        "高等数学", (datetime.now() + timedelta(minutes=20)).time(),
        config_path=config_path, speak=False,
    )

    assert result["ok"] is True
    assert result["data_source"] == "mock"
    assert "高等数学课" in result["advice"]
    assert result["audio"] is None

    log_path = tmp_path / "runs.jsonl"
    assert log_path.exists()
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["course"] == "高等数学"
    assert record["provider"] == "mock"


def test_gene_advice_qweather_failure_degrades(tmp_path, monkeypatch):
    """异常：真实接口返回 None 时不再回退 mock，而是播报断网提示。"""
    monkeypatch.setattr(weather, "get_weather",
                        lambda *a, **k: {"weather_now": None, "minutely": None})
    config_path = write_config(tmp_path, provider="qweather", api_key="real-key-for-test")

    result = weather.gene_advice(
        "英语", (datetime.now() + timedelta(minutes=20)).time(),
        config_path=config_path, speak=False,
    )
    assert result["data_source"] == "qweather-failed"
    assert "无法获取天气数据" in result["advice"]


def test_gene_advice_auto_news(tmp_path, monkeypatch):
    """FR-12：config.news.enabled 时自动抓取资讯拼进建议；关闭时不抓取。"""
    import news

    calls = []

    def fake_collect(city_key=None, limit=6, force=False, ttl_minutes=30):
        calls.append((city_key, limit))
        return {"city": city_key, "updated": "2026-10-23 08:00", "stale": False,
                "items": [{"title": "大连地铁1号线今日延长运营时间", "local": True}]}

    monkeypatch.setattr(news, "collect", fake_collect)

    config_on = write_config(tmp_path, news={"enabled": True, "limit": 3})
    result = weather.gene_advice(
        "高等数学", (datetime.now() + timedelta(minutes=20)).time(),
        config_path=config_on, speak=False,
    )
    assert calls == [("dalian", 3)]
    assert "本地资讯" in result["advice"]
    assert "地铁" in result["advice"]

    config_off = write_config(tmp_path, news={"enabled": False})
    weather.gene_advice(
        "英语", (datetime.now() + timedelta(minutes=20)).time(),
        config_path=config_off, speak=False,
    )
    assert len(calls) == 1


def test_gene_advice_switches_city(tmp_path):
    """地区切换：city_key 决定天气样例与返回值，不再固定单一城市。"""
    config_path = write_config(tmp_path, cities={
        "dalian": {"city": "101070201", "location": "121.52,38.88"},
        "beijing": {"city": "101010100", "location": "116.41,39.90"},
    })
    beijing = weather.gene_advice(
        "高等数学", (datetime.now() + timedelta(minutes=20)).time(),
        config_path=config_path, speak=False, city_key="beijing",
    )
    dalian = weather.gene_advice(
        "高等数学", (datetime.now() + timedelta(minutes=20)).time(),
        config_path=config_path, speak=False, city_key="dalian",
    )
    assert beijing["city"] == "beijing"
    assert dalian["city"] == "dalian"
    assert beijing["weather"]["weather_now"]["now"]["text"] != dalian["weather"]["weather_now"]["now"]["text"]
