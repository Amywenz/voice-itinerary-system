"""FastAPI Web 控制台：把 CLI 能力可视化，并补充课程管理、天气预览、语音工坊等页面。

启动：.venv\\Scripts\\python.exe -m uvicorn webapp.main:app --port 8000
"""
from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, time, timedelta

import soundfile as sf
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import play
import news
import tts as tts_module
import voices
import weather
from course import Schedule, WEEKDAY_NAMES, courses_on, load_weekly, sync_day, today_weekday

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "webapp")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

app = FastAPI(
    title="行程播报系统 API",
    description="基于 OpenVoice 的课程行程语音播报系统",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=os.path.join(WEB_DIR, "static")), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
templates = Jinja2Templates(directory=os.path.join(WEB_DIR, "templates"))


def _asset_version() -> str:
    """静态资源版本号：取 static 目录内最新修改时间，文件一改浏览器缓存自动失效。"""
    latest = 0.0
    static_dir = os.path.join(WEB_DIR, "static")
    for root, _dirs, files in os.walk(static_dir):
        for name in files:
            latest = max(latest, os.path.getmtime(os.path.join(root, name)))
    return str(int(latest))


templates.env.globals["asset_version"] = _asset_version()


# ----------------------------------------------------------------------
# 请求模型
# ----------------------------------------------------------------------
class CourseIn(BaseModel):
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    course_name: str = Field(min_length=1, max_length=40)


class TriggerIn(BaseModel):
    course: str | None = None
    course_time: str | None = None
    city: str | None = None
    lang: str = "zh-CN"
    voice: str | None = None   # 语音工坊选中的全站音色，留空则用该语言默认音色
    style: str = "natural"
    mode: str = "fast"   # fast=Piper/SAPI 秒级；clone=OpenVoice 音色克隆（较慢）


class AdviceIn(BaseModel):
    city: str | None = None


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=800)
    engine: str = "auto"
    speed: float = Field(default=1.0, ge=0.7, le=1.3)


class VoiceTTSIn(BaseModel):
    """多语言试听：与主链路 /api/tts 分离，输出独立 wav，不覆盖 advice.wav。"""
    text: str = Field(min_length=1, max_length=800)
    lang: str = "zh-CN"
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.7, le=1.3)
    style: str = "natural"


class WeeklySyncIn(BaseModel):
    weekday: int | None = Field(default=None, ge=1, le=7)


class ConfigIn(BaseModel):
    provider: str | None = None
    api_key: str | None = None
    default_city: str | None = None
    tts_engine: str | None = None
    speed: float | None = Field(default=None, ge=0.7, le=1.3)


# ----------------------------------------------------------------------
# 内部工具
# ----------------------------------------------------------------------
def _schedule() -> Schedule:
    return Schedule()


def _load_config() -> dict:
    return weather.load_config()


def _save_config(config: dict) -> None:
    path = os.path.join(BASE_DIR, "config.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)


def _next_course(schedule: Schedule):
    """返回下一节尚未开始的课程；今天的课都过了，就顺延到明天第一节。"""
    now = datetime.now()
    items = schedule.to_list()
    for item in items:
        if datetime.fromisoformat(item["datetime"]) >= now:
            return item
    if not items:
        return None
    first = dict(items[0])
    first["datetime"] = (datetime.fromisoformat(first["datetime"])
                         + timedelta(days=1)).isoformat(timespec="minutes")
    return first


def _future_time(minutes: int) -> time:
    return (datetime.now() + timedelta(minutes=minutes)).time()


def _city_or_default(city: str | None, config: dict | None = None) -> str:
    """把 URL 上的城市校验成配置里的合法值，非法或空就回退默认城市。"""
    config = config or _load_config()
    cities = config.get("cities") or {}
    if city in cities:
        return city
    return config.get("default_city", "dalian")


def _weather_snapshot(city_key: str | None = None) -> dict:
    config = _load_config()
    city_key = _city_or_default(city_key, config)
    city_conf = (config.get("cities") or {}).get(city_key, {})
    provider = config.get("provider", "mock")
    api_key = str(config.get("api_key", ""))
    data_source = "mock"

    if provider == "qweather" and api_key and api_key != weather.PLACEHOLDER_KEY:
        data = weather.get_weather(api_key, city=city_conf.get("city"),
                                   location=city_conf.get("location"))
        data_source = "qweather"
        if data.get("weather_now") is None:
            data_source = "qweather-failed"
    else:
        data = weather.get_mock_weather(city_key)

    next_course = _next_course(_schedule())
    course_name = next_course["course_name"] if next_course else "自习"
    if next_course:
        course_time = datetime.fromisoformat(next_course["datetime"]).time()
    else:
        course_time = _future_time(20)

    advice = weather.generate_weather_advice(
        data if data_source != "qweather-failed" else None,
        course_name, course_time,
        # 预览不得覆盖交付用的 resources/weather.txt
        output_dir=os.path.join(BASE_DIR, "outputs", "preview"),
    )
    # 本地实时资讯：拼进建议文本，同时单独返回给页面做资讯卡
    news_data = news.collect(city_key, 6)
    advice = news.append_to_advice(advice, news_data["items"])
    now_info = (data or {}).get("weather_now", {}).get("now", {}) if data else {}
    return {
        "city_key": city_key,
        "data_source": data_source,
        "advice": advice,
        "weather": data,
        "now": now_info,
        "news": news_data,
    }


def _read_weather_text() -> str:
    path = os.path.join(BASE_DIR, "resources", "weather.txt")
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def _read_logs(limit: int = 50) -> list[dict]:
    path = os.path.join(BASE_DIR, "data", "runs.jsonl")
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return list(reversed(records[-limit:]))


def _status() -> dict:
    weights = tts_module.check_weights()
    audio_path = os.path.join(OUTPUT_DIR, "advice.wav")
    audio = None
    if os.path.exists(audio_path):
        info = sf.info(audio_path)
        audio = {
            "sample_rate": info.samplerate,
            "duration": round(info.frames / info.samplerate, 2),
            "size_kb": round(os.path.getsize(audio_path) / 1024, 1),
        }
    try:
        import torch
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        torch_version = torch.__version__
    except Exception:
        device, torch_version = "unavailable", "未安装"
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "weights": weights,
        "torch": torch_version,
        "device": device,
        "simpleaudio": play.sa is not None,
        "audio": audio,
        "meta": _read_meta(),
    }


def _read_meta() -> dict:
    path = os.path.join(OUTPUT_DIR, "tts_meta.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _read_voice_meta() -> dict:
    """多语言试听最近一次的指标（outputs/voice_meta.json）。"""
    path = os.path.join(OUTPUT_DIR, "voice_meta.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


# ----------------------------------------------------------------------
# 页面
# ----------------------------------------------------------------------
@app.get("/")
def dashboard(request: Request, city: str | None = None):
    config = _load_config()
    cities = config.get("cities") or {}
    schedule = _schedule()
    courses = schedule.to_list()
    next_course = _next_course(schedule)
    snapshot = _weather_snapshot(city if city in cities else None)
    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "active": "/",
        "courses": courses,
        "next_course": next_course,
        "snapshot": snapshot,
        "status": _status(),
        "weather_text": _read_weather_text(),
        "now": datetime.now(),
        "cities": cities,
        "city_key": snapshot["city_key"],
        "catalog": voices.catalog(),
    })


@app.get("/stage")
def stage_page(request: Request, city: str | None = None):
    """可视化大屏：聚合课程、天气、语音与播报日志，供演示时投屏。"""
    config = _load_config()
    cities = config.get("cities") or {}
    schedule = _schedule()
    logs = _read_logs(200)
    today = datetime.now().strftime("%Y-%m-%d")
    today_runs = sum(1 for row in logs if str(row.get("time", "")).startswith(today))
    snapshot = _weather_snapshot(_city_or_default(city, config))
    points = ((snapshot.get("weather") or {}).get("minutely") or {}).get("minutely") or []
    rain_expected = any(float(p.get("precip", 0) or 0) > 0 for p in points)
    return templates.TemplateResponse(request=request, name="stage.html", context={
        "active": "/stage",
        "courses": schedule.to_list(),
        "next_course": _next_course(schedule),
        "snapshot": snapshot,
        "status": _status(),
        "logs": logs[:4],
        "today_runs": today_runs,
        "rain_expected": rain_expected,
        "now": datetime.now(),
        "cities": cities,
        "city_key": snapshot["city_key"],
    })


@app.get("/courses")
def courses_page(request: Request):
    schedule = _schedule()
    weekly = load_weekly()
    weekdays = [
        {"index": i, "name": WEEKDAY_NAMES[i - 1], "courses": courses_on(weekly, i)}
        for i in range(1, 6)
    ]
    return templates.TemplateResponse(request=request, name="courses.html", context={
        "active": "/courses",
        "courses": schedule.to_list(),
        "next_course": _next_course(schedule),
        "weekdays": weekdays,
        "today": today_weekday(),
        "today_name": WEEKDAY_NAMES[today_weekday() - 1],
        "now": datetime.now(),
    })


@app.get("/todo")
def todo_page(request: Request):
    """今日待办：轻量记录，数据保存在浏览器本地，不上传服务器。"""
    return templates.TemplateResponse(request=request, name="todo.html", context={
        "active": "/todo",
        "now": datetime.now(),
    })


@app.get("/focus")
def focus_page(request: Request):
    """专注计时：番茄钟，帮助安排学习与休息。"""
    return templates.TemplateResponse(request=request, name="focus.html", context={
        "active": "/focus",
        "now": datetime.now(),
    })


@app.get("/weather")
def weather_page(request: Request, city: str | None = None):
    config = _load_config()
    snapshot = _weather_snapshot(_city_or_default(city, config))
    return templates.TemplateResponse(request=request, name="weather.html", context={
        "active": "/weather",
        "snapshot": snapshot,
        "cities": config.get("cities", {}),
        "city_key": snapshot["city_key"],
        "weather_text": _read_weather_text(),
        "config": config,
    })


@app.get("/studio")
def studio_page(request: Request):
    config = _load_config()
    reference = config.get("reference_speaker", "resources/ly2.wav")
    segments = []
    seg_dir = os.path.join(OUTPUT_DIR, "segments")
    if os.path.isdir(seg_dir):
        segments = sorted(os.listdir(seg_dir))
    return templates.TemplateResponse(request=request, name="studio.html", context={
        "active": "/studio",
        "config": config,
        "text": _read_weather_text(),
        "meta": _read_meta(),
        "reference": reference,
        "segments": segments,
        "status": _status(),
        "catalog": voices.catalog(),
        "voice_meta": _read_voice_meta(),
    })


@app.get("/settings")
def settings_page(request: Request):
    config = _load_config()
    return templates.TemplateResponse(request=request, name="settings.html", context={
        "active": "/settings",
        "config": config,
        "status": _status(),
    })


@app.get("/logs")
def logs_page(request: Request):
    return templates.TemplateResponse(request=request, name="logs.html", context={
        "active": "/logs",
        "logs": _read_logs(),
    })


@app.get("/news")
def news_page(request: Request, city: str | None = None):
    """本地实时资讯页：RSS 抓取结果 + 城市切换 + 手动刷新。"""
    config = _load_config()
    city_key = _city_or_default(city, config)
    snapshot = _weather_snapshot(city_key)
    news_data = snapshot.get("news") or {}
    return templates.TemplateResponse(request=request, name="news.html", context={
        "active": "/news",
        "snapshot": snapshot,
        "news": news_data,
        "cities": config.get("cities", {}),
        "city_key": city_key,
    })


# ----------------------------------------------------------------------
# API
# ----------------------------------------------------------------------
@app.get("/api/status")
def api_status():
    return _status()


@app.get("/api/courses")
def api_courses():
    return _schedule().to_list()


@app.post("/api/courses")
def api_add_course(payload: CourseIn):
    try:
        course_time = datetime.strptime(payload.time, "%H:%M").time()
        time_str = _schedule().add_course(course_time, payload.course_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "time": time_str}


@app.delete("/api/courses/{time_str}")
def api_delete_course(time_str: str):
    if not _schedule().remove_course(time_str):
        raise HTTPException(status_code=404, detail="课程不存在")
    return {"ok": True}


@app.post("/api/courses/demo")
def api_demo_courses():
    schedule = _schedule()
    schedule.clear()
    demo = [
        (_future_time(60), "高等数学"),
        (_future_time(180), "大学物理"),
        (_future_time(300), "程序设计"),
    ]
    for course_time, name in demo:
        schedule.add_course(course_time, name)
    return {"ok": True, "courses": schedule.to_list()}


@app.get("/api/weekly")
def api_weekly():
    """返回周课表，按星期分组；weekday 1=周一 … 7=周日。"""
    weekly = load_weekly()
    return {
        "weekday": today_weekday(),
        "days": {str(i): courses_on(weekly, i) for i in range(1, 8)},
    }


@app.post("/api/weekly/sync")
def api_weekly_sync(payload: WeeklySyncIn | None = None):
    """把周课表中指定星期（默认今天）的课同步为当前课程表。"""
    weekday = (payload.weekday if payload else None) or today_weekday()
    schedule = _schedule()
    synced = sync_day(schedule, load_weekly(), weekday)
    return {"ok": True, "weekday": weekday, "count": len(synced),
            "courses": schedule.to_list()}


@app.post("/api/trigger")
def api_trigger(payload: TriggerIn):
    """一键播报：fast 用 Piper/SAPI 秒级出声，clone 走 OpenVoice 音色克隆。

    fast 不加载 torch，输出 outputs/voice_broadcast.wav；
    clone 保留原链路，输出 outputs/advice.wav（评分红线证据文件）。
    """
    schedule = _schedule()
    next_course = _next_course(schedule)
    if payload.course:
        course_name = payload.course
        if payload.course_time:
            course_dt = datetime.combine(
                datetime.now().date(),
                datetime.strptime(payload.course_time, "%H:%M").time(),
            )
        else:
            course_dt = datetime.now() + timedelta(minutes=10)
        course_time = course_dt.time()
    elif next_course:
        course_name = next_course["course_name"]
        course_dt = datetime.fromisoformat(next_course["datetime"])
        course_time = course_dt.time()
    else:
        raise HTTPException(status_code=400, detail="课程表为空，请先添加课程")

    config = _load_config()
    cities = config.get("cities") or {}
    city_key = payload.city if payload.city in cities else config.get("default_city", "dalian")
    started = datetime.now()

    try:
        # 快速播报只读资讯缓存，不为了几条标题去等三次 RSS 请求
        news_items = news.collect(city_key, 6,
                                 cache_only=payload.mode != "clone")["items"]
        if payload.mode == "clone":
            result = weather.gene_advice(course_name, course_time,
                                         news_items=news_items, city_key=city_key)
            return {
                "ok": True,
                "mode": "clone",
                "city": city_key,
                "course": course_name,
                "advice": result["advice"],
                "spoken": result["advice"],
                "engine": result["engine"],
                "voice": "音色克隆",
                "style": "natural",
                "duration": (result.get("tts") or {}).get("duration"),
                "audio": f"/outputs/advice.wav?v={int(datetime.now().timestamp())}",
                "tts": result["tts"],
                "elapsed": round((datetime.now() - started).total_seconds(), 2),
            }

        # 快速路径：只跑无模型链路 + Piper/SAPI，避免 CPU 上 OpenVoice 的十几秒等待
        result = weather.gene_advice(course_name, course_time, news_items=news_items,
                                     city_key=city_key, speak=False)
        now_info = (((result.get("weather") or {}).get("weather_now") or {}).get("now") or {})
        course_dt = datetime.combine(datetime.now().date(), course_time)
        if course_dt < datetime.now():
            course_dt += timedelta(days=1)      # 今天已过点：下一节是明天同一时刻
        minutes = max(int((course_dt - datetime.now()).total_seconds() / 60), 0)
        spoken = voices.broadcast_text(
            payload.lang, course_name, minutes, now_info.get("feelsLike"),
            now_info.get("text", ""), cities.get(city_key, {}).get("name", ""),
            city_key, result["advice"], weather_data=result.get("weather"),
        )
        meta = voices.synthesize(spoken, payload.lang, voice_id=payload.voice, style=payload.style,
                                 out_path=os.path.join(OUTPUT_DIR, "voice_broadcast.wav"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"播报失败：{exc}") from exc

    return {
        "ok": True,
        "mode": "fast",
        "city": city_key,
        "course": course_name,
        "advice": result["advice"],
        "spoken": spoken,
        "engine": meta["engine"],
        "voice": meta["voice_name"],
        "style": meta.get("style_name", "自然"),
        "duration": meta["duration"],
        "audio": voices.audio_url(meta),
        "fallback_reason": meta.get("fallback_reason", ""),
        "elapsed": round((datetime.now() - started).total_seconds(), 2),
    }


@app.get("/api/news")
def api_news(city: str | None = None, limit: int = 6, refresh: bool = False):
    """本地资讯：默认读 30 分钟缓存，refresh=true 时强制抓取。"""
    city_key = city or _load_config().get("default_city", "dalian")
    if city_key not in news.CITY_KEYWORDS:
        raise HTTPException(status_code=400, detail=f"不支持的城市：{city_key}")
    limit = max(1, min(limit, 12))
    return news.collect(city_key, limit, force=refresh)


@app.get("/api/voices")
def api_voices(lang: str | None = None):
    """语言与音色清单，available/reason 由本机实际能力决定。"""
    data = voices.catalog()
    if lang:
        data["languages"] = [row for row in data["languages"] if row["code"] == lang]
    return data


@app.post("/api/voice/tts")
def api_voice_tts(payload: VoiceTTSIn):
    """多语言试听：输出 outputs/voice_<id>.wav，成功返回可播放 URL。"""
    try:
        meta = voices.synthesize(payload.text, payload.lang, payload.voice,
                                 payload.speed, style=payload.style)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"语音合成失败：{exc}") from exc
    return {"ok": True, "meta": meta, "audio": voices.audio_url(meta)}


@app.get("/api/weather")
def api_weather(city: str | None = None):
    snapshot = _weather_snapshot(_city_or_default(city))
    return {
        "city": snapshot["city_key"],
        "source": snapshot["data_source"],
        "now": snapshot["now"],
        "advice": snapshot["advice"],
    }


@app.post("/api/advice")
def api_advice(payload: AdviceIn):
    return api_weather(payload.city)


@app.post("/api/tts")
def api_tts(payload: TTSIn):
    config = _load_config()
    config["tts_engine"] = payload.engine
    config["speed"] = payload.speed
    try:
        meta = tts_module.tts(config, text=payload.text, engine=payload.engine)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"语音合成失败：{exc}") from exc
    return {
        "ok": True,
        "meta": meta,
        "audio": f"/outputs/advice.wav?v={int(datetime.now().timestamp())}",
    }


@app.post("/api/tts/from-weather")
def api_tts_from_weather():
    config = _load_config()
    try:
        meta = tts_module.tts(config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"语音合成失败：{exc}") from exc
    return {"ok": True, "meta": meta,
            "audio": f"/outputs/advice.wav?v={int(datetime.now().timestamp())}"}


@app.get("/api/logs")
def api_logs(limit: int = 50):
    return _read_logs(limit)


@app.get("/api/config")
def api_get_config():
    config = _load_config()
    config["api_key"] = "已配置" if config.get("api_key") not in (
        "", weather.PLACEHOLDER_KEY) else weather.PLACEHOLDER_KEY
    return config


@app.post("/api/config")
def api_set_config(payload: ConfigIn):
    config = _load_config()
    data = payload.model_dump(exclude_none=True)

    if data.get("provider") not in (None, "mock", "qweather"):
        raise HTTPException(status_code=400, detail="provider 只能是 mock 或 qweather")
    if data.get("tts_engine") not in (None, "auto", "openvoice", "sapi"):
        raise HTTPException(status_code=400, detail="tts_engine 只能是 auto/openvoice/sapi")
    if "default_city" in data and data["default_city"] not in (config.get("cities") or {}):
        raise HTTPException(status_code=400, detail="城市代码不在 cities 列表中")
    if data.get("api_key") in ("", "已配置"):
        data.pop("api_key", None)

    config.update(data)
    _save_config(config)
    return {"ok": True}


@app.get("/health")
def health():
    return JSONResponse({"status": "ok", "time": datetime.now().isoformat(timespec="seconds")})
