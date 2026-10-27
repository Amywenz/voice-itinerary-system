"""天气与建议模块测试：8/28 边界、雨雪判断、断网降级、字段缺失、接口组织。"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest
import requests

import weather


def mock_payload(feels_like: str = "26", text: str = "多云") -> dict:
    data = copy.deepcopy(weather.MOCK_WEATHER)
    data["weather_now"]["now"]["feelsLike"] = feels_like
    data["weather_now"]["now"]["text"] = text
    return data


def future_time(minutes: int = 20):
    return (datetime.now() + timedelta(minutes=minutes)).time()


@pytest.mark.parametrize("feels,expected", [
    ("7.9", "请注意保暖"),
    ("8", "气温适宜"),
    ("20", "气温适宜"),
    ("28", "气温适宜"),
    ("28.1", "请注意防暑"),
])
def test_feels_like_boundaries(tmp_path, feels, expected):
    """FR-03 边界：<8 保暖、8 与 28 适宜、>28 防暑。"""
    advice = weather.generate_weather_advice(
        mock_payload(feels_like=feels), "高等数学", future_time(), str(tmp_path)
    )
    assert expected in advice
    assert "高等数学课" in advice


def test_past_course_time_rolls_to_next_day(tmp_path):
    """下一节课今天已过点时应顺延到明天，播报不能出现“0分钟之后”。"""
    past = datetime.now() - timedelta(minutes=30)
    normalized = weather._normalize_course_time(past)
    assert normalized > datetime.now()
    advice = weather.generate_weather_advice(
        mock_payload(), "高等数学", past, str(tmp_path)
    )
    assert "小时" in advice                     # 顺延后至少 23 小时，不再是 0 分钟
    assert "高等数学课" in advice


def test_far_future_course_uses_hour_unit(tmp_path):
    """距离超过一小时用“X小时Y分钟”，比“520分钟之后”更自然。"""
    advice = weather.generate_weather_advice(
        mock_payload(), "高等数学", datetime.now() + timedelta(minutes=130), str(tmp_path)
    )
    assert "2小时" in advice


def test_describe_conditions_shares_rain_and_temp_branches():
    """结构化判定与中文建议同源：外语播报复用同一套温度/降水结论。"""
    cold = weather.describe_conditions(mock_payload(feels_like="7.9", text="小雨"))
    assert cold["data_ok"] is True
    assert cold["temp_level"] == "cold"
    assert cold["rain"] == "now_rain"

    mild = weather.describe_conditions(mock_payload(feels_like="26"))
    assert mild["temp_level"] == "mild"
    assert mild["rain"] == "none"
    assert weather.describe_conditions(None)["data_ok"] is False


def test_current_rain_adds_umbrella(tmp_path):
    advice = weather.generate_weather_advice(
        mock_payload(text="小雨"), "英语", future_time(), str(tmp_path)
    )
    assert "正在下雨" in advice
    assert "请带伞" in advice


def test_current_snow_adds_umbrella_and_clothes(tmp_path):
    advice = weather.generate_weather_advice(
        mock_payload(text="中雪"), "英语", future_time(), str(tmp_path)
    )
    assert "正在下雪" in advice
    assert "穿多点衣服" in advice


def test_minutely_rain_uses_fromisoformat(tmp_path):
    """FR-04：未来 10 分钟有降水时，用 fromisoformat 解析 +08:00 时间。"""
    data = mock_payload(text="多云")
    rain_at = datetime.now(timezone(timedelta(hours=8))) + timedelta(minutes=10)
    data["minutely"]["minutely"] = [
        {"fxTime": rain_at.isoformat(timespec="minutes"), "precip": "0.6", "type": "rain"}
    ]
    advice = weather.generate_weather_advice(data, "高等数学", future_time(), str(tmp_path))
    assert "分钟后可能会下雨" in advice
    assert "带伞" in advice


def test_no_rain_falls_back_to_no_umbrella(tmp_path):
    advice = weather.generate_weather_advice(
        mock_payload(text="多云"), "高等数学", future_time(), str(tmp_path)
    )
    assert "未来两小时没有降水" in advice


def test_weather_txt_is_written(tmp_path):
    advice = weather.generate_weather_advice(
        mock_payload(), "高等数学", future_time(), str(tmp_path)
    )
    text_path = tmp_path / "weather.txt"
    assert text_path.exists()
    assert text_path.read_text(encoding="utf-8") == advice


def test_fetch_weather_data_returns_none_on_network_error(monkeypatch):
    """异常：网络错误返回 None，而不是抛异常中断播报。"""
    def boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("断网")

    monkeypatch.setattr(weather.requests, "get", boom)
    assert weather.fetch_weather_data("https://example.com") is None


def test_fetch_weather_data_raises_for_status(monkeypatch):
    """异常：非 2xx 状态码必须触发 raise_for_status 并返回 None。"""
    class FakeResponse:
        def raise_for_status(self):
            raise requests.exceptions.HTTPError("403")

    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: FakeResponse())
    assert weather.fetch_weather_data("https://example.com") is None


def test_get_weather_requires_city():
    with pytest.raises(ValueError):
        weather.get_weather("key")


def test_get_weather_organizes_two_endpoints(monkeypatch):
    """FR-03：字典推导同时组织 weather_now / minutely 两个接口。"""
    seen = []

    def fake_fetch(url):
        seen.append(url)
        return {"url": url}

    monkeypatch.setattr(weather, "fetch_weather_data", fake_fetch)
    result = weather.get_weather("k", city="101070201", location="121.52,38.88")
    assert set(result.keys()) == {"weather_now", "minutely"}
    assert len(seen) == 2


def test_get_weather_without_location_skips_minutely(monkeypatch):
    monkeypatch.setattr(weather, "fetch_weather_data", lambda url: {"ok": True})
    result = weather.get_weather("k", city="101070201")
    assert set(result.keys()) == {"weather_now"}


def test_offline_none_data_degrades(tmp_path):
    """异常：data=None 时给出可播报的降级文案，不抛异常。"""
    advice = weather.generate_weather_advice(None, "高等数学", future_time(), str(tmp_path))
    assert "无法获取天气数据" in advice
    assert "高等数学课" in advice


def test_missing_fields_degrades(tmp_path):
    """异常：接口返回体缺 feelsLike 时降级，不 KeyError。"""
    data = mock_payload()
    del data["weather_now"]["now"]["feelsLike"]
    advice = weather.generate_weather_advice(data, "高等数学", future_time(), str(tmp_path))
    assert "天气数据不完整" in advice


def test_format_temperature():
    assert weather.format_temperature("26") == "26"
    assert weather.format_temperature("26.0") == "26"
    assert weather.format_temperature(26.5) == "26.5"
