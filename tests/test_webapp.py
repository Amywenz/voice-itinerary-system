"""Web 控制台接口测试：页面渲染、课程 CRUD、配置校验、资讯与多语言接口。"""
from __future__ import annotations

from fastapi.testclient import TestClient
import soundfile as sf

import voices
from webapp.main import app

client = TestClient(app)


def test_pages_render():
    for path in ["/", "/stage", "/courses", "/todo", "/focus", "/weather", "/news", "/studio", "/settings", "/logs"]:
        response = client.get(path)
        assert response.status_code == 200
        assert "行程播报" in response.text


def test_status_endpoint():
    data = client.get("/api/status").json()
    assert data["python"].startswith("3.11")
    assert len(data["weights"]["files"]) == 5


def test_course_crud():
    client.delete("/api/courses/07:05")
    created = client.post("/api/courses", json={"time": "07:05", "course_name": "接口测试课"})
    assert created.status_code == 200
    courses = client.get("/api/courses").json()
    assert any(c["time"] == "07:05" and c["course_name"] == "接口测试课" for c in courses)

    deleted = client.delete("/api/courses/07:05")
    assert deleted.status_code == 200
    assert all(c["time"] != "07:05" for c in client.get("/api/courses").json())


def test_course_validation():
    assert client.post("/api/courses", json={"time": "9:00", "course_name": "x"}).status_code == 422
    assert client.post("/api/courses", json={"time": "09:00", "course_name": ""}).status_code == 422


def test_config_rejects_unknown_provider():
    response = client.post("/api/config", json={"provider": "unknown"})
    assert response.status_code == 400


def test_tts_requires_text():
    assert client.post("/api/tts", json={"text": ""}).status_code == 422


def test_weather_endpoint():
    data = client.get("/api/weather?city=dalian").json()
    assert data["city"] == "dalian"
    assert data["source"] in ("mock", "qweather", "qweather-failed")
    assert "课" in data["advice"]


def test_weekly_endpoint():
    data = client.get("/api/weekly").json()
    assert data["weekday"] in range(1, 8)
    assert set(data["days"].keys()) == {str(i) for i in range(1, 8)}


def test_news_endpoint_returns_items():
    data = client.get("/api/news?city=dalian&limit=3").json()
    assert data["city"] == "dalian"
    assert isinstance(data["items"], list)
    assert len(data["items"]) <= 3


def test_news_endpoint_rejects_unknown_city():
    assert client.get("/api/news?city=mars").status_code == 400


def test_voices_endpoint_lists_languages():
    data = client.get("/api/voices").json()
    codes = {row["code"] for row in data["languages"]}
    assert {"zh-CN", "en-US", "es-ES", "yue"} <= codes
    assert set(data["engines"]) == {"edge", "piper", "sapi", "openvoice", "cloud"}


def test_voice_tts_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(
        voices, "_piper_tts",
        lambda text, model, out_path, speed: sf.write(out_path, [0.0] * 4410, 22050),
    )
    monkeypatch.setattr(voices, "CACHE_PATH", str(tmp_path / "voice_meta.json"))
    response = client.post("/api/voice/tts", json={
        "text": "Good morning", "lang": "en-US", "voice": "en-ryan", "speed": 1.0,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["engine"] == "piper"
    assert data["audio"].startswith("/outputs/voice_en-ryan.wav")


def test_voice_tts_rejects_bad_language():
    response = client.post("/api/voice/tts", json={"text": "hi", "lang": "xx-YY"})
    assert response.status_code == 400
