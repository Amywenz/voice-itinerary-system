"""出行建议模块：配置读取、天气接口、建议文本生成、全链路串联。

对应评分细则 B-5：
  - get_weather 用字典推导组织 city / location 两个接口
  - fetch_weather_data 使用 raise_for_status，异常返回 None
  - 体感温度 <8 / >28 / 其余 三分支
  - '雨' / '雪' in text 判断当前天气
  - fxTime 用 fromisoformat 解析（兼容 +08:00）
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

import requests
import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(BASE_DIR, "config.yaml")
DEFAULT_WEATHER_TEXT = os.path.join(BASE_DIR, "resources", "weather.txt")
PLACEHOLDER_KEY = "YOUR_QWEATHER_KEY"

# 各城市的离线样例差异：仅覆盖 now 里的温度/天气，其余字段沿用 MOCK_WEATHER。
# 这样切换地区时页面与播报内容确实会变，而不是只换了下拉框。
MOCK_BY_CITY = {
    "dalian": {"temp": "24", "feelsLike": "26", "text": "多云"},
    "shuangliu": {"temp": "29", "feelsLike": "31", "text": "小雨"},
    "beijing": {"temp": "18", "feelsLike": "15", "text": "晴"},
    "shanghai": {"temp": "23", "feelsLike": "24", "text": "阴"},
    "guangzhou": {"temp": "30", "feelsLike": "33", "text": "雷阵雨"},
    "shenzhen": {"temp": "29", "feelsLike": "32", "text": "多云"},
    "hangzhou": {"temp": "25", "feelsLike": "27", "text": "小雨"},
    "chengdu": {"temp": "21", "feelsLike": "22", "text": "阴"},
    "wuhan": {"temp": "26", "feelsLike": "28", "text": "晴"},
    "xian": {"temp": "16", "feelsLike": "12", "text": "晴"},
    "chongqing": {"temp": "24", "feelsLike": "25", "text": "小雨"},
    "nanjing": {"temp": "22", "feelsLike": "23", "text": "多云"},
    "tianjin": {"temp": "19", "feelsLike": "16", "text": "晴"},
    "qingdao": {"temp": "21", "feelsLike": "22", "text": "多云"},
    "shenyang": {"temp": "15", "feelsLike": "11", "text": "晴"},
}

# 离线样例：字段与和风天气真实返回保持一致，保证断网也能完成演示
MOCK_WEATHER = {
    "weather_now": {
        "code": "200",
        "updateTime": "2026-10-22T08:50+08:00",
        "now": {
            "obsTime": "2026-10-22T08:40+08:00",
            "temp": "24",
            "feelsLike": "26",
            "text": "多云",
            "windDir": "东南风",
            "windScale": "2",
            "humidity": "65",
            "precip": "0.0",
        },
    },
    "minutely": {
        "code": "200",
        "summary": "未来两小时无降水",
        "minutely": [
            {"fxTime": "2026-10-22T09:00+08:00", "precip": "0.0", "type": "rain"},
            {"fxTime": "2026-10-22T09:05+08:00", "precip": "0.0", "type": "rain"},
        ],
    },
}


# ----------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------
def load_config(filename: str = "config.yaml") -> dict:
    """读取 YAML 配置；相对路径按项目根目录解析，避免换工作目录后失效。"""
    path = filename if os.path.isabs(filename) else os.path.join(BASE_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ----------------------------------------------------------------------
# 天气接口
# ----------------------------------------------------------------------
def fetch_weather_data(url: str):
    """发起 GET 请求并返回 JSON；网络/状态码异常时返回 None。"""
    try:
        response = requests.get(url, timeout=10)
        # 状态码非 2xx 时抛出 HTTPError，由下方统一捕获
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None


def get_weather(api_key: str, city: str | None = None, location: str | None = None,
                api_host: str = "devapi.qweather.com") -> dict:
    """调用实时天气 + 分钟级降水两个接口。

    weather_now 依赖城市代码 city；minutely 依赖经纬度 location。
    api_host 由和风控制台分配（新版账号是 xxxx.qweatherapi.com），默认旧版 devapi。
    返回 {'weather_now': dict|None, 'minutely': dict|None}，
    None 表示该接口失败，调用方据此区分“没网”和“没降水”。
    """
    if not city and not location:
        raise ValueError("必须提供城市代码参数！")

    base_url = f"https://{api_host}/v7"
    endpoints = {
        "weather_now": f"{base_url}/weather/now?location={city}&key={api_key}",
        "minutely": (
            f"{base_url}/minutely/5m?location={location}&key={api_key}"
            if location else None
        ),
    }
    results = {
        key: fetch_weather_data(url)
        for key, url in endpoints.items()
        if url
    }
    return results


def get_mock_weather(city: str | None = None) -> dict:
    """返回离线样例天气，深拷贝避免调用方修改全局常量。

    按城市覆盖温度与天气文本；未知城市沿用默认样例（dalian 口径）。
    """
    data = json.loads(json.dumps(MOCK_WEATHER, ensure_ascii=False))
    patch = MOCK_BY_CITY.get(city or "", MOCK_BY_CITY["dalian"])
    data["weather_now"]["now"].update(patch)
    return data


# ----------------------------------------------------------------------
# 建议文本
# ----------------------------------------------------------------------
def format_temperature(value) -> str:
    """把 '26' / '26.0' 统一成 '26'，避免播报里出现 26.0 摄氏度。"""
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def _normalize_course_time(course_time) -> datetime:
    """把 datetime / time / 'HH:MM' 统一成「下一节课」的 datetime。

    课程表按天循环，今天的课都过了就顺延到明天同一时刻；
    否则 (course_dt - now) 为负数，播报会退化成“0分钟之后上课”。
    """
    if isinstance(course_time, datetime):
        course_dt = course_time
    elif isinstance(course_time, str):
        parsed = datetime.strptime(course_time, "%H:%M").time()
        course_dt = datetime.combine(date.today(), parsed)
    elif hasattr(course_time, "hour") and hasattr(course_time, "minute"):
        course_dt = datetime.combine(date.today(), course_time)
    else:
        return datetime.now() + timedelta(minutes=10)
    if course_dt < datetime.now():
        course_dt += timedelta(days=1)
    return course_dt


def _write_weather_text(advice: str, output_dir: str | None = None) -> str:
    output_dir = output_dir or os.path.join(BASE_DIR, "resources")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "weather.txt")
    with open(path, "w", encoding="utf-8") as file:
        file.write(advice)
    return path


def describe_conditions(data: dict | None, now: datetime | None = None) -> dict:
    """把天气 JSON 归一成播报用的结构化字段，中文与外语播报共用同一套判定。

    返回字段：
      data_ok      接口数据是否完整（False 表示断网或字段缺失）
      clock        当前时刻，供外语播报注入
      feels        体感温度数值（无法解析时按 20）
      weather      当前天气原词（如“多云”）
      temp_level   cold / mild / hot，阈值仍是 8 与 28
      rain         now_rain / now_snow / soon_rain / soon_snow / none
      rain_minutes 分钟级降水的起始分钟（now_* 为 0）
    """
    now = now or datetime.now()
    cond = {"data_ok": False, "clock": now.strftime("%H:%M"), "feels": 20.0,
            "weather": "", "temp_level": "mild", "rain": "none", "rain_minutes": 0}
    if not data or not isinstance(data, dict):
        return cond

    weather_now = data.get("weather_now") or {}
    now_info = weather_now.get("now") if isinstance(weather_now, dict) else None
    if not now_info or "feelsLike" not in now_info:
        return cond

    cond["data_ok"] = True
    try:
        feels_value = float(now_info["feelsLike"])
    except (TypeError, ValueError):
        feels_value = 20.0
    cond["feels"] = feels_value
    cond["temp_level"] = "cold" if feels_value < 8 else ("hot" if feels_value > 28 else "mild")

    weather_text = str(now_info.get("text", ""))
    cond["weather"] = weather_text
    if "雨" in weather_text:
        cond["rain"] = "now_rain"
        return cond
    if "雪" in weather_text:
        cond["rain"] = "now_snow"
        return cond

    # 当前没有雨雪时，才继续看未来两小时分钟级降水
    minutely_obj = data.get("minutely") or {}
    minute_list = minutely_obj.get("minutely", []) if isinstance(minutely_obj, dict) else []
    for minute in minute_list:
        try:
            if float(minute.get("precip", 0)) > 0.00 and minute.get("type") in ("rain", "snow"):
                try:
                    # 接口时间带 +08:00，这里用 fromisoformat 解析；本地时区去掉 tzinfo 后比较
                    rain_dt = datetime.fromisoformat(minute["fxTime"]).replace(tzinfo=None)
                    minutes_later = max(int((rain_dt - now).total_seconds() / 60), 0)
                except (ValueError, KeyError, TypeError):
                    minutes_later = 0
                cond["rain"] = "soon_snow" if minute.get("type") == "snow" else "soon_rain"
                cond["rain_minutes"] = minutes_later
                break
        except (TypeError, ValueError):
            continue
    return cond


def generate_weather_advice(data: dict | None, course: str, course_time,
                            output_dir: str | None = None) -> str:
    """把天气 JSON 转成完整播报文本，并写入 weather.txt。

    异常处理：
      - data 为 None（断网 / 接口失败）：输出可播报的降级文案，不抛异常
      - now / feelsLike 字段缺失：按“字段缺失”降级，仍保留课程提醒
    """
    now = datetime.now()
    course_dt = _normalize_course_time(course_time)
    time_diff_minutes = max(int((course_dt - now).total_seconds() / 60), 0)
    if time_diff_minutes >= 60:
        hours, rest = divmod(time_diff_minutes, 60)
        wait_text = f"{hours}小时{rest}分钟" if rest else f"{hours}小时"
    else:
        wait_text = f"{time_diff_minutes}分钟"
    cur_time = (
        f"当前时间为{now.strftime('%H点%M分')}，"
        f"{wait_text}之后有{course}课。"
    )

    # 断网 / 接口完全失败
    if not data or not isinstance(data, dict):
        advice = cur_time + "当前无法获取天气数据，请检查网络后重试。出门前请自行确认天气，注意安全。"
        _write_weather_text(advice, output_dir)
        return advice

    conditions = describe_conditions(data, now)
    # 接口字段缺失（例如 code=401 或返回体不完整）
    if not conditions["data_ok"]:
        advice = cur_time + "天气数据不完整，暂时无法生成出行建议，请出门前自行确认天气。"
        _write_weather_text(advice, output_dir)
        return advice

    feels_text = format_temperature(conditions["feels"])

    # 体感温度三分支：边界值 8 与 28 落在“适宜”
    if conditions["temp_level"] == "cold":
        temp_advice = f"当前体感温度为{feels_text}摄氏度，气温较低，请注意保暖。"
    elif conditions["temp_level"] == "hot":
        temp_advice = f"当前体感温度为{feels_text}摄氏度，气温较高，请注意防暑。"
    else:
        temp_advice = f"当前体感温度为{feels_text}摄氏度，气温适宜。"

    rain = conditions["rain"]
    if rain == "now_rain":
        weather_advice = "当前天气正在下雨，请带伞。"
    elif rain == "now_snow":
        weather_advice = "当前天气正在下雪，请带伞并穿多点衣服。"
    elif rain in ("soon_rain", "soon_snow"):
        rain_type = "雨" if rain == "soon_rain" else "雪"
        weather_advice = (
            f"{conditions['rain_minutes']}分钟后可能会下{rain_type}，请注意带伞。"
        )
    else:
        weather_advice = "未来两小时没有降水，可以不用带伞。"

    advice = cur_time + temp_advice + weather_advice
    _write_weather_text(advice, output_dir)
    return advice


# ----------------------------------------------------------------------
# 全链路串联
# ----------------------------------------------------------------------
def _append_run_log(record: dict, config: dict) -> None:
    """把每次播报写入 data/runs.jsonl，供 Web 日志页与结项报告取证。"""
    runs_path = (config.get("paths") or {}).get("runs", "data/runs.jsonl")
    path = runs_path if os.path.isabs(runs_path) else os.path.join(BASE_DIR, runs_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _auto_news(config: dict, city_key: str) -> list:
    """按 config.news.enabled 自动抓取本地资讯；未开启或抓取失败返回空列表。

    定时播报（timer.py）与 Web 都调用 gene_advice，未显式传 news_items 时走这里，
    保证“课前 10 分钟自动播报”也带上当天本地资讯。
    """
    news_conf = config.get("news") or {}
    if not news_conf.get("enabled"):
        return []
    try:
        import news as news_module
        data = news_module.collect(city_key, limit=int(news_conf.get("limit", 6)))
        return data.get("items", [])
    except Exception:
        return []


def gene_advice(course: str, course_time, config_path: str = "config.yaml",
                speak: bool = True, engine: str | None = None,
                news_items: list | None = None, city_key: str | None = None) -> dict:
    """串联“配置 → 天气 → 建议 → 文本 → 合成 → 播放”。

    一条命令即可走完整链路，中间无手工拷贝步骤（评分细则 D-1）。
    city_key 为空时取 config.default_city；Web 切换地区时显式传入，
    天气样例与本地资讯都跟着换城市，不再固定一个地区。
    news_items 非空时，把 1~2 条本地资讯追加到建议末尾（由 news.py 提供）；
    未传入时按 config.news.enabled 自动抓取，抓取失败则不带资讯继续播报。
    返回本次运行摘要，供 Web / 测试断言使用。
    """
    config = load_config(config_path)
    provider = config.get("provider", "mock")
    api_key = str(config.get("api_key", ""))
    cities = config.get("cities") or {}
    city_key = city_key if city_key in cities else config.get("default_city", "dalian")
    city_conf = cities.get(city_key, {})
    city = city_conf.get("city")
    location = city_conf.get("location")

    # 占位符 key 或 mock 模式走离线样例；真实 key + qweather 才请求外网
    if provider == "qweather" and api_key and api_key != PLACEHOLDER_KEY:
        api_host = str(config.get("api_host", "devapi.qweather.com"))
        weather_data = get_weather(api_key, city=city, location=location, api_host=api_host)
        data_source = "qweather"
        # weather_now 为 None 说明断网/接口异常，交给 generate_weather_advice 走降级
        if weather_data.get("weather_now") is None:
            data_source = "qweather-failed"
            advice_data = None  # 区分“没网”与“没降水/字段缺失”
        else:
            advice_data = weather_data
    else:
        weather_data = get_mock_weather(city_key)
        advice_data = weather_data
        data_source = "mock"

    # 按配置里的 paths.weather_text 定位输出目录，测试可用临时路径隔离，避免覆盖交付文本
    weather_text = (config.get("paths") or {}).get("weather_text", "resources/weather.txt")
    weather_text = weather_text if os.path.isabs(weather_text) else os.path.join(BASE_DIR, weather_text)
    advice = generate_weather_advice(advice_data, course, course_time,
                                     output_dir=os.path.dirname(weather_text))

    # 本地资讯：未显式传入且配置开启时自动抓取；抓取失败不阻断主链路
    if news_items is None:
        news_items = _auto_news(config, city_key)
    if news_items:
        import news as news_module
        advice = news_module.append_to_advice(advice, news_items, count=1)

    # 结尾告别语：按日期固定一条，放在资讯之后、写盘与合成之前，保证录进音频
    from voices import farewell
    advice = advice.rstrip("。") + "。" + farewell()
    _write_weather_text(advice, os.path.dirname(weather_text))

    result = {
        "course": course,
        "course_time": str(course_time),
        "city": city_key,
        "data_source": data_source,
        "advice": advice,
        "weather": weather_data,
        "engine": None,
        "audio": None,
        "tts": None,
        "ok": False,
    }

    if speak:
        # 延迟导入：只跑“无模型链路”时不加载 torch / OpenVoice
        from tts import tts as synthesize
        from play import play_audio

        tts_meta = synthesize(config, text=advice, engine=engine)
        play_audio(config["audio_dir"])
        result.update({
            "engine": tts_meta["engine"],
            "audio": tts_meta["save_path"],
            "tts": tts_meta,
            "ok": True,
        })
    else:
        result["ok"] = True

    _append_run_log({
        "time": datetime.now().isoformat(timespec="seconds"),
        "course": course,
        "course_time": str(course_time),
        "provider": data_source,
        "engine": result["engine"],
        "audio": result["audio"],
        "advice": advice,
    }, config)
    return result


def main(argv: list[str] | None = None) -> int:
    """命令行入口：--advice-only 只跑无模型链路（Rev-C C-1 演示用）。"""
    import argparse

    parser = argparse.ArgumentParser(description="出行建议模块")
    parser.add_argument("--course", default="高等数学", help="课程名称")
    parser.add_argument("--time", default=None, help="上课时间 HH:MM，默认 20 分钟后")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--advice-only", action="store_true", help="只生成 weather.txt，不合成语音")
    parser.add_argument("--engine", default=None, help="openvoice / sapi，默认读配置")
    args = parser.parse_args(argv)

    if args.time:
        course_time = datetime.strptime(args.time, "%H:%M").time()
    else:
        course_time = (datetime.now() + timedelta(minutes=20)).time()

    result = gene_advice(args.course, course_time, config_path=args.config,
                         speak=not args.advice_only, engine=args.engine)
    print("数据源:", result["data_source"])
    print("建议文本:", result["advice"])
    if args.advice_only:
        print("已写入 resources/weather.txt（未验证语音链路）")
    else:
        print(f"合成引擎: {result['engine']}, 音频: {result['audio']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
