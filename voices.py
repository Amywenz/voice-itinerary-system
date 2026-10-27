"""多语言 / 多音色语音层：语言注册表 + Piper / SAPI / OpenVoice / 云 TTS 适配。

定位：`tts.py` 仍是评分要求的主链路（OpenVoice 两级流程，输出 advice.wav）。
本模块负责“探索型”能力：普通话以外的英语、西班牙语与粤语，
并把结果写到 outputs/voice_preview.wav 等独立文件，绝不覆盖 advice.wav 证据。

引擎能力（本机实测）：
  - edge    微软神经网络音色（edge-tts），多语言 + 真粤语，需联网，无需 Key
  - piper    离线，多语言（中/英/西），模型放 voices/，由 scripts/download_voices.py 下载
  - sapi     Windows 系统语音，仅中/英
  - openvoice 音色克隆，沿用 tts.py 的两级流程与参考音频
  - cloud    云 TTS：腾讯云 TextToVoice（TC3 签名）或通用 HTTP 网关；未配置 Key 时明确报“需配置”并降级
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import tempfile
import wave
from datetime import date, datetime

import soundfile as sf
import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VOICE_DIR = os.path.join(BASE_DIR, "voices")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
CACHE_PATH = os.path.join(OUTPUT_DIR, "voice_meta.json")

# 语言注册表：flag 用于界面展示，sample 是试听默认文案
LANGUAGES = {
    "zh-CN": {
        "name": "普通话",
        "native": "普通话",
        "flag": "🇨🇳",
        "sample": "早上好，距离高等数学课还有十分钟，今天多云，体感二十六度，适合出门。",
    },
    "en-US": {
        "name": "英语",
        "native": "English",
        "flag": "🇬🇧",
        "sample": "Good morning. Your calculus class starts in ten minutes. "
                  "It is cloudy and twenty-six degrees outside.",
    },
    "es-ES": {
        "name": "西班牙语",
        "native": "Español",
        "flag": "🇪🇸",
        "sample": "Buenos días. Tu clase de matemáticas empieza en diez minutos. "
                  "Hace veintiséis grados y el cielo está nublado.",
    },
    "yue": {
        "name": "粤语",
        "native": "粵語",
        "flag": "🇭🇰",
        "sample": "早晨，距離高等數學課仲有十分鐘，今日多雲，記得帶遮。",
        "needs": "sapi/cloud",
    },
}

# 音色清单：engine 决定怎么合成，model 对应 voices/<model>.onnx 或 edge 的 ShortName
# edge 音色排在各语言第一位：默认优先用神经网络音色，音质明显好于 Piper
VOICES = [
    {"id": "zh-xiaoxiao", "lang": "zh-CN", "name": "晓晓", "gender": "女声",
     "engine": "edge", "model": "zh-CN-XiaoxiaoNeural", "desc": "神经网络音色，温柔自然（推荐）"},
    {"id": "zh-yunxi", "lang": "zh-CN", "name": "云希", "gender": "男声",
     "engine": "edge", "model": "zh-CN-YunxiNeural", "desc": "神经网络男声，年轻清亮"},
    {"id": "zh-xiaoyi", "lang": "zh-CN", "name": "晓伊", "gender": "少女声",
     "engine": "edge", "model": "zh-CN-XiaoyiNeural", "desc": "神经网络少女音，适合萝莉角色"},
    {"id": "zh-yunjian", "lang": "zh-CN", "name": "云健", "gender": "成熟男声",
     "engine": "edge", "model": "zh-CN-YunjianNeural", "desc": "神经网络男声，低沉厚重"},
    {"id": "zh-yunyang", "lang": "zh-CN", "name": "云扬", "gender": "播音男声",
     "engine": "edge", "model": "zh-CN-YunyangNeural", "desc": "神经网络播音腔男声"},
    {"id": "zh-huayan", "lang": "zh-CN", "name": "华言", "gender": "女声",
     "engine": "piper", "model": "zh_CN-huayan-medium", "desc": "离线中文，断网时保底"},
    {"id": "zh-clone", "lang": "zh-CN", "name": "音色克隆", "gender": "参考音色",
     "engine": "openvoice", "model": "", "desc": "OpenVoice 两级流程，克隆 resources/ly2.wav"},
    {"id": "zh-huihui", "lang": "zh-CN", "name": "慧慧", "gender": "女声",
     "engine": "sapi", "model": "Microsoft Huihui Desktop", "desc": "Windows 系统语音，零依赖"},
    {"id": "en-aria", "lang": "en-US", "name": "Aria", "gender": "女声",
     "engine": "edge", "model": "en-US-AriaNeural", "desc": "神经网络美式英语女声（推荐）"},
    {"id": "en-guy", "lang": "en-US", "name": "Guy", "gender": "男声",
     "engine": "edge", "model": "en-US-GuyNeural", "desc": "神经网络美式英语男声"},
    {"id": "en-lessac", "lang": "en-US", "name": "Lessac", "gender": "女声",
     "engine": "piper", "model": "en_US-lessac-medium", "desc": "离线美式英语，断网时保底"},
    {"id": "en-ryan", "lang": "en-US", "name": "Ryan", "gender": "男声",
     "engine": "piper", "model": "en_US-ryan-medium", "desc": "离线美式英语，适合长句"},
    {"id": "en-clone", "lang": "en-US", "name": "音色克隆", "gender": "参考音色",
     "engine": "openvoice", "model": "", "desc": "同一参考音色说英语"},
    {"id": "es-elvira", "lang": "es-ES", "name": "Elvira", "gender": "女声",
     "engine": "edge", "model": "es-ES-ElviraNeural", "desc": "神经网络西班牙语女声（推荐）"},
    {"id": "es-alvaro", "lang": "es-ES", "name": "Alvaro", "gender": "男声",
     "engine": "edge", "model": "es-ES-AlvaroNeural", "desc": "神经网络西班牙语男声"},
    {"id": "es-dave", "lang": "es-ES", "name": "Dave", "gender": "男声",
     "engine": "piper", "model": "es_ES-davefx-medium", "desc": "离线卡斯蒂利亚西班牙语"},
    {"id": "es-sharvard", "lang": "es-ES", "name": "Sharvard", "gender": "女声",
     "engine": "piper", "model": "es_ES-sharvard-medium", "desc": "离线西班牙语女声"},
    {"id": "yue-hiumaan", "lang": "yue", "name": "曉曼", "gender": "女声",
     "engine": "edge", "model": "zh-HK-HiuMaanNeural", "desc": "真粤语神经网络女声（推荐）"},
    {"id": "yue-wanlung", "lang": "yue", "name": "雲龍", "gender": "男声",
     "engine": "edge", "model": "zh-HK-WanLungNeural", "desc": "真粤语神经网络男声"},
    {"id": "yue-sapi", "lang": "yue", "name": "粤语系统语音", "gender": "系统音色",
     "engine": "sapi", "model": "zh-HK", "desc": "需在 Windows 安装「中文(香港)」语音包"},
    {"id": "yue-cloud", "lang": "yue", "name": "粤语云合成", "gender": "腾讯云 智彤",
     "engine": "cloud", "model": "", "desc": "腾讯云 TTS 101019，需 Key；未配置时降级"},
]

# 角色化音色预设：在本机音色之上做音高/语速/机械调制，得到“萝莉音/大叔音/播音腔”等
# pitch 单位为半音（正数更高），tempo >1 更快，robot=True 加环形调制 + 幅值量化
STYLES = [
    {"id": "natural", "name": "自然", "desc": "原始音色，不做修饰",
     "pitch": 0.0, "tempo": 1.0, "robot": False},
    {"id": "anchor_f", "name": "播音腔女声", "desc": "明亮清晰，语速略慢",
     "pitch": 1.0, "tempo": 0.95, "robot": False},
    {"id": "anchor_m", "name": "播音腔男声", "desc": "低沉稳重，语速略慢",
     "pitch": -2.0, "tempo": 0.95, "robot": False},
    {"id": "loli", "name": "萝莉音", "desc": "音调偏高，语速轻快",
     "pitch": 2.0, "tempo": 1.06, "robot": False},
    {"id": "uncle", "name": "大叔音", "desc": "音调偏低，语速放缓",
     "pitch": -2.0, "tempo": 0.92, "robot": False},
    {"id": "robot", "name": "机械音", "desc": "金属调制 + 数字量化",
     "pitch": -1.0, "tempo": 1.0, "robot": True},
]
DEFAULT_STYLE = "natural"

# 角色 → edge 神经网络音色：有真人音色就不做变调，避免上一版 ±6 半音造成的失真
STYLE_VOICES = {
    "anchor_f": {"zh-CN": "zh-xiaoxiao", "yue": "yue-hiumaan"},
    "anchor_m": {"zh-CN": "zh-yunyang", "yue": "yue-wanlung"},
    "loli": {"zh-CN": "zh-xiaoyi"},
    "uncle": {"zh-CN": "zh-yunjian", "yue": "yue-wanlung"},
}

# 播报文案模板：中文直接播完整建议；其他语言按“时段 → 当前时间 → 课程倒计时 → 体感建议
# → 降水提醒 → 本地资讯 → 告别语”逐句拼，句量和中文一致（约 30 秒），
# 保证换语言后听到的是该语言，而不是中文被外语音色硬读。
BROADCAST_TEMPLATES = {
    "zh-CN": {
        "intro": "现在是{clock}，距离{course}课还有{wait}。",
        "temp": {
            "cold": "{city}当前体感温度{feels}摄氏度，气温较低，请注意保暖。",
            "mild": "{city}当前体感温度{feels}摄氏度，气温适宜，穿件薄外套就够。",
            "hot": "{city}当前体感温度{feels}摄氏度，气温较高，请注意防暑多喝水。",
        },
        "rain": {
            "now_rain": "当前天气正在下雨，请带伞。",
            "now_snow": "当前天气正在下雪，请带伞并穿多点衣服。",
            "soon_rain": "{minutes}分钟后可能会下雨，请注意带伞。",
            "soon_snow": "{minutes}分钟后可能会下雪，请注意带伞。",
            "none": "未来两小时没有降水，可以不用带伞。",
            "unavailable": "天气数据暂时获取不到，出门前请自行确认天气。",
            "unknown": "",
        },
        "news": "今天{city}的本地资讯已经同步到资讯页面，播报结束后可以查看。",
    },
    "en-US": {
        "intro": "{period}. It is {clock} now, and {course} starts in {wait}.",
        "temp": {
            "cold": "In {city} it feels like {feels} degrees and the weather is {weather}, "
                    "so it is quite chilly, please dress warmly.",
            "mild": "In {city} it feels like {feels} degrees and the weather is {weather}, "
                    "so the temperature is comfortable and light clothing is enough.",
            "hot": "In {city} it feels like {feels} degrees and the weather is {weather}, "
                   "so it is rather hot, stay cool and drink plenty of water.",
        },
        "rain": {
            "now_rain": "It is raining right now, so remember to take an umbrella.",
            "now_snow": "It is snowing right now, so take an umbrella and dress warmly.",
            "soon_rain": "Rain may start in about {minutes} minutes, so bring an umbrella just in case.",
            "soon_snow": "Snow may start in about {minutes} minutes, so bring an umbrella just in case.",
            "none": "No rain is expected in the next two hours, so you can leave your umbrella at home.",
            "unavailable": "Weather data is temporarily unavailable, so please check the weather "
                           "yourself before heading out.",
            "unknown": "",
        },
        "news": "Local headlines for {city} are ready on the news page, "
                "take a look after this broadcast.",
    },
    "es-ES": {
        "intro": "{period}. Son las {clock} y {course} empieza dentro de {wait}.",
        "temp": {
            "cold": "En {city} la sensación térmica es de {feels} grados y el tiempo está {weather}, "
                    "hace bastante frío, así que abrígate bien.",
            "mild": "En {city} la sensación térmica es de {feels} grados y el tiempo está {weather}, "
                    "la temperatura es agradable, lleva ropa ligera.",
            "hot": "En {city} la sensación térmica es de {feels} grados y el tiempo está {weather}, "
                   "hace bastante calor, así que mantente fresco y bebe agua.",
        },
        "rain": {
            "now_rain": "Ahora mismo está lloviendo, así que no olvides el paraguas.",
            "now_snow": "Ahora mismo está nevando, lleva el paraguas y abrígate bien.",
            "soon_rain": "Puede empezar a llover en unos {minutes} minutos, "
                         "así que lleva el paraguas por si acaso.",
            "soon_snow": "Puede empezar a nevar en unos {minutes} minutos, "
                         "así que lleva el paraguas por si acaso.",
            "none": "No se esperan lluvias en las próximas dos horas, "
                    "puedes dejar el paraguas en casa.",
            "unavailable": "Los datos del tiempo no están disponibles ahora mismo, "
                           "consulta el tiempo antes de salir.",
            "unknown": "",
        },
        "news": "Las noticias de {city} están en la página de noticias, "
                "míralas después del boletín.",
    },
    "yue": {
        "intro": "{period}，而家係{clock}，你嘅{course}課仲有{wait}就開始。",
        "temp": {
            "cold": "{city}而家體感{feels}度，天氣{weather}，都幾凍，記得着多件衫。",
            "mild": "{city}而家體感{feels}度，天氣{weather}，溫度啱啱好，着輕便啲就得。",
            "hot": "{city}而家體感{feels}度，天氣{weather}，天氣幾熱，記得補水同避暑。",
        },
        "rain": {
            "now_rain": "而家落緊雨，出門口記得帶遮。",
            "now_snow": "而家落緊雪，記得帶遮兼着多件衫。",
            "soon_rain": "{minutes}分鐘之後可能會落雨，最好帶定把遮。",
            "soon_snow": "{minutes}分鐘之後可能會落雪，最好帶定把遮。",
            "none": "未來兩個鐘都冇雨水，可以唔使帶遮。",
            "unavailable": "暫時攞唔到天氣資料，出門口之前記得自己睇一睇天氣。",
            "unknown": "",
        },
        "news": "今日{city}嘅本地新聞已經放咗喺資訊頁，播完之後可以睇下。",
    },
}

# 时段问候：英语/西语的播报开头要带 Good morning / Buenos días
PERIODS = {
    "en-US": ("Good morning", "Good afternoon", "Good evening"),
    "es-ES": ("Buenos días", "Buenas tardes", "Buenas noches"),
    "yue": ("朝早", "下晝", "夜晚"),
    "zh-CN": ("早上", "下午", "晚上"),
}

# 倒计时单位：与中文“8小时5分钟”对齐，外语写成 “8 hours and 5 minutes”
WAIT_UNITS = {
    "zh-CN": ("小时", "分钟"),
    "yue": ("小時", "分鐘"),
    "en-US": ("hours", "minutes"),
    "es-ES": ("horas", "minutos"),
}

# 每日告别语：结尾统一追加，按日期固定取一条（同一天多次播报一致，跨天自动换）
FAREWELLS = {
    "zh-CN": [
        "最后祝你有开心的一天，事事顺利，感谢收听。",
        "今天的播报就到这里，祝你一天好心情，万事顺意，感谢收听。",
        "以上就是今天的行程播报，愿你今天顺顺利利，心情明亮，感谢收听。",
        "播报结束，祝你今天笑容常在，诸事顺遂，感谢你的收听。",
        "今天就聊到这里，愿你一路顺风，事事称心，感谢收听。",
        "播报完毕，祝你今天元气满满，所遇皆美好，感谢收听。",
        "最后祝你今天开心，工作顺利，平安喜乐，感谢收听。",
        "感谢收听今天的播报，愿你事事顺心，天天都有好天气。",
    ],
    "en-US": [
        "That's all for today. Wishing you a happy and productive day. Thanks for listening.",
        "This is the end of today's briefing. Have a wonderful day ahead. Thanks for listening.",
        "Thanks for listening. May your day be smooth, bright and full of good news.",
    ],
    "es-ES": [
        "Esto es todo por hoy. Que tengas un día feliz y productivo. Gracias por escuchar.",
        "Termina el boletín de hoy. Que tengas un gran día. Gracias por escuchar.",
        "Gracias por escuchar. Que tu día sea tranquilo, luminoso y lleno de buenas noticias.",
    ],
    "yue": [
        "今日嘅播報就講到呢度，祝你一日開心，事事順利，多謝收聽。",
        "播報完喇，祝你今日順順利利，心情靚靚，多謝收聽。",
        "多謝收聽今日嘅播報，祝你事事稱心，日日都有好天氣。",
    ],
}


def farewell(lang: str = "zh-CN", on: date | None = None) -> str:
    """按日期固定选一条告别语：同一天多次播报保持一致，跨天自动换一条。"""
    lines = FAREWELLS.get(lang) or FAREWELLS["zh-CN"]
    day = on or date.today()
    return lines[random.Random(day.toordinal()).randrange(len(lines))]


# 天气词表：英文/西班牙语播报需要把“多云/小雨”之类的接口原词替换掉
WEATHER_LABELS = {
    "en-US": {"多云": "cloudy", "晴": "sunny", "阴": "overcast", "小雨": "light rain",
              "中雨": "moderate rain", "大雨": "heavy rain", "雷阵雨": "thunder showers",
              "雪": "snow", "雾": "fog", "霾": "haze"},
    "es-ES": {"多云": "nublado", "晴": "soleado", "阴": "cubierto", "小雨": "lluvia ligera",
              "中雨": "lluvia moderada", "大雨": "lluvia fuerte", "雷阵雨": "tormenta",
              "雪": "nieve", "雾": "niebla", "霾": "calima"},
}

PLACEHOLDER_KEYS = {"", "YOUR_CLOUD_KEY", "YOUR_TTS_KEY",
                    "YOUR_TENCENT_SECRET_ID", "YOUR_TENCENT_SECRET_KEY"}


# ----------------------------------------------------------------------
# 配置与可用性
# ----------------------------------------------------------------------
def _read_yaml(name: str) -> dict:
    path = os.path.join(BASE_DIR, name)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_cloud_config() -> dict:
    """读取云 TTS 配置；config.local.yaml 里的同名字段覆盖 config.yaml。"""
    cloud = dict(_read_yaml("config.yaml").get("cloud_tts") or {})
    local = _read_yaml("config.local.yaml").get("cloud_tts") or {}
    if isinstance(local, dict):
        cloud.update(local)
    return cloud


def cloud_ready() -> bool:
    """云 TTS 是否可用：通用网关看 api_key，腾讯云看 SecretId + SecretKey。"""
    cloud = load_cloud_config()
    if not cloud.get("provider") or not cloud.get("endpoint"):
        return False
    if cloud.get("provider") == "tencent":
        return (str(cloud.get("secret_id", "")) not in PLACEHOLDER_KEYS
                and str(cloud.get("secret_key", "")) not in PLACEHOLDER_KEYS)
    return str(cloud.get("api_key", "")) not in PLACEHOLDER_KEYS


def edge_ready() -> bool:
    """edge-tts 是否可用：装了包 + 有可用神经网络音色（需联网）。"""
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


def piper_ready(model: str) -> bool:
    if not model:
        return False
    return (os.path.exists(os.path.join(VOICE_DIR, f"{model}.onnx"))
            and os.path.exists(os.path.join(VOICE_DIR, f"{model}.onnx.json")))


def openvoice_ready() -> bool:
    import tts as tts_module
    return bool(tts_module.check_weights()["available"])


_SAPI_VOICE_CACHE: list | None = None


def sapi_voices(force: bool = False) -> list[dict]:
    """列出 Windows 已安装的系统语音（name/culture）；非 Windows 返回空列表。"""
    global _SAPI_VOICE_CACHE
    if _SAPI_VOICE_CACHE is not None and not force:
        return _SAPI_VOICE_CACHE
    if os.name != "nt":
        _SAPI_VOICE_CACHE = []
        return []
    script = ("Add-Type -AssemblyName System.Speech;"
              "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices()"
              "|ForEach-Object{$_.VoiceInfo.Name+'|'+$_.VoiceInfo.Culture}")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8", errors="ignore")
    except Exception:
        _SAPI_VOICE_CACHE = []
        return []
    rows = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if "|" in line:
            name, culture = line.rsplit("|", 1)
            rows.append({"name": name.strip(), "culture": culture.strip()})
    _SAPI_VOICE_CACHE = rows
    return rows


def sapi_voice_for(model: str) -> str:
    """把音色配置解析成实际安装的 SAPI 语音名，找不到返回空字符串。

    model 两种写法：
      - 完整语音名（Microsoft Huihui Desktop）→ 精确匹配；
      - 文化标签（zh-HK）→ 匹配已安装语音的文化前缀，用于粤语等方言语音包。
    """
    rows = sapi_voices()
    if not rows:
        return ""
    want = (model or "").strip()
    if not want:
        return ""
    for row in rows:
        if row["name"].lower() == want.lower():
            return row["name"]
    for row in rows:
        if row["culture"].lower().startswith(want.lower()):
            return row["name"]
    return ""


def voice_available(voice: dict) -> tuple[bool, str]:
    engine = voice.get("engine")
    if engine == "edge":
        return (True, "") if edge_ready() else (
            False, "未安装 edge-tts，运行 pip install edge-tts")
    if engine == "piper":
        return (True, "") if piper_ready(voice["model"]) else (
            False, "模型未下载，运行 scripts/download_voices.py")
    if engine == "sapi":
        if os.name != "nt":
            return False, "仅 Windows 支持 SAPI"
        if not sapi_voice_for(voice["model"]):
            return False, (f"系统未安装语音「{voice['model']}」，"
                           "请在 Windows 设置里安装对应语音包")
        return True, ""
    if engine == "openvoice":
        return (True, "") if openvoice_ready() else (
            False, "OpenVoice 权重缺失，运行 scripts/download_models.py")
    if engine == "cloud":
        return (True, "") if cloud_ready() else (
            False, "需配置 cloud_tts.provider / endpoint / api_key")
    return False, f"未知引擎：{engine}"


def _public_voice(voice: dict) -> dict:
    ok, reason = voice_available(voice)
    row = dict(voice)
    row["available"] = ok
    row["reason"] = reason
    return row


def list_voices(lang: str | None = None) -> list[dict]:
    rows = [_public_voice(v) for v in VOICES]
    if lang:
        rows = [v for v in rows if v["lang"] == lang]
    return rows


def catalog() -> dict:
    """给 Web 用的完整清单：语言 + 音色 + 角色风格 + 引擎能力。"""
    return {
        "languages": [
            {"code": code, **meta,
             "voices": [v for v in list_voices(code)]}
            for code, meta in LANGUAGES.items()
        ],
        "styles": STYLES,
        "engines": {
            "edge": edge_ready(),
            "piper": any(piper_ready(m) for m in
                         (v["model"] for v in VOICES if v["engine"] == "piper")),
            "sapi": os.name == "nt",
            "openvoice": openvoice_ready(),
            "cloud": cloud_ready(),
        },
    }


def get_voice(voice_id: str) -> dict:
    for voice in VOICES:
        if voice["id"] == voice_id:
            return voice
    raise ValueError(f"未知音色：{voice_id}")


def default_voice(lang: str) -> str:
    """该语言下第一个可用音色；都不可用时返回清单里的第一个。"""
    rows = list_voices(lang)
    for row in rows:
        if row["available"]:
            return row["id"]
    return rows[0]["id"] if rows else "zh-huayan"


def get_style(style_id: str | None) -> dict:
    """按 id 取风格预设；未知风格回退自然，避免页面选项与后端口径不一致时报错。"""
    for style in STYLES:
        if style["id"] == (style_id or DEFAULT_STYLE):
            return style
    return STYLES[0]


def weather_label(text: str, lang: str) -> str:
    """把中文天气词翻成目标语言的播报词；没有映射时原样返回。"""
    table = WEATHER_LABELS.get(lang) or {}
    for zh, foreign in table.items():
        if zh in (text or ""):
            return foreign
    return text or ""


# 天气词没有映射时的兜底词，避免模板出现“the weather is ,”这种断句
WEATHER_FALLBACK = {"en-US": "unclear", "es-ES": "variable", "yue": "一般", "zh-CN": "未知"}


def _period_text(hour: int, lang: str) -> str:
    """按时段给问候词：英语 Good morning/afternoon/evening，粤语朝早/下晝/夜晚。"""
    names = PERIODS.get(lang) or PERIODS["zh-CN"]
    if 5 <= hour < 12:
        return names[0]
    if 12 <= hour < 18:
        return names[1]
    return names[2]


def _clock_text(now: datetime, lang: str) -> str:
    """当前时刻口语化：英语念 11:54 PM，粤语念 23點54分，避免数字串被逐位读出。"""
    if lang == "en-US":
        return now.strftime("%I:%M %p").lstrip("0")
    if lang == "yue":
        return f"{now.hour}點{now.minute:02d}分"
    if lang == "zh-CN":
        return f"{now.hour}点{now.minute:02d}分"
    # 西语念 12 小时制，"0:13" 这类写法会被逐个数字读出来
    return f"{now.hour % 12 or 12}:{now.minute:02d}"


def _wait_text(minutes: int, lang: str) -> str:
    """倒计时口语化：中文“8小时5分钟”，英语“8 hours and 5 minutes”。"""
    hours_unit, minutes_unit = WAIT_UNITS.get(lang) or WAIT_UNITS["zh-CN"]
    hours, rest = divmod(max(int(minutes), 0), 60)
    if lang in ("en-US", "es-ES"):
        joiner = "and" if lang == "en-US" else "y"
        if hours and rest:
            return f"{hours} {hours_unit} {joiner} {rest} {minutes_unit}"
        if hours:
            return f"{hours} {hours_unit}"
        return f"{rest} {minutes_unit}"
    if hours and rest:
        return f"{hours}{hours_unit}{rest}{minutes_unit}"
    if hours:
        return f"{hours}{hours_unit}"
    return f"{rest}{minutes_unit}"


def _course_text(course: str, lang: str) -> str:
    """英西语音色读不了中文课程名，改说“下一节课”，避免整段发音崩掉。"""
    if lang in ("en-US", "es-ES") and any("\u4e00" <= ch <= "\u9fff" for ch in course):
        return {"en-US": "your next class", "es-ES": "tu próxima clase"}[lang]
    return course


def _temp_level(feels: float) -> str:
    return "cold" if feels < 8 else ("hot" if feels > 28 else "mild")


def broadcast_text(lang: str, course: str, minutes: int, feels, weather_text: str,
                   city_name: str = "", city_key: str = "", advice: str = "",
                   weather_data: dict | None = None, now: datetime | None = None) -> str:
    """生成该语言的播报文本（结尾统一带一条当日告别语）。

    中文直接用 gene_advice 产出的完整建议（含降水、本地资讯与告别语）；
    其他语言按“时段/时间 → 倒计时 → 体感建议 → 降水提醒 → 本地资讯”逐句拼，
    句量与中文一致，weather_data 传入原始 JSON 时与中文共用 describe_conditions 判定。
    """
    if lang == "zh-CN" and advice:
        return advice
    lang = lang if lang in BROADCAST_TEMPLATES else "zh-CN"
    template = BROADCAST_TEMPLATES[lang]
    now = now or datetime.now()
    try:
        feels_value = float(feels)
    except (TypeError, ValueError):
        feels_value = 20.0
    feels_text = str(int(round(feels_value)))

    if lang in ("zh-CN", "yue"):
        city = city_name or city_key
    else:
        city = (city_key or "").replace("shuangliu", "Shuangliu").replace("xian", "Xi'an").title()

    if weather_data is not None:
        # 延迟导入避免 voices ↔ weather 循环依赖
        from weather import describe_conditions
        conditions = describe_conditions(weather_data, now)
        if conditions["data_ok"]:
            rain_key, rain_minutes = conditions["rain"], conditions["rain_minutes"]
            temp_level = conditions["temp_level"]
        else:
            rain_key, rain_minutes, temp_level = "unavailable", 0, _temp_level(feels_value)
    else:
        # 只有体感温度（单测/预览）：不臆造降水结论
        rain_key, rain_minutes, temp_level = "unknown", 0, _temp_level(feels_value)

    weather_word = weather_label(weather_text, lang) or WEATHER_FALLBACK.get(lang, "")
    parts = [
        template["intro"].format(
            period=_period_text(now.hour, lang),
            clock=_clock_text(now, lang),
            course=_course_text(course, lang),
            wait=_wait_text(minutes, lang),
        ),
        template["temp"][temp_level].format(
            city=city, feels=feels_text, weather=weather_word,
        ),
        template["rain"].get(rain_key, "").format(minutes=rain_minutes),
    ]
    if city:
        parts.append(template["news"].format(city=city))

    # 中文/粤语句子之间不需要空格；英西语句末要留一个空格再接告别语
    separator = "" if lang in ("zh-CN", "yue") else " "
    text = separator.join(part for part in parts if part)
    return text + separator + farewell(lang)


# ----------------------------------------------------------------------
# 风格处理（音高 / 语速 / 机械音）
# ----------------------------------------------------------------------
def _robotize(data, sr: int):
    """环形调制 + 幅值量化，做出机械音的金属感。"""
    import numpy as np

    t = np.arange(len(data)) / sr
    carrier = np.sin(2 * np.pi * 70 * t).astype("float32")
    modulated = data * (0.6 + 0.4 * carrier)
    levels = 24
    return np.round(modulated * levels) / levels


def _apply_style(path: str, style_id: str) -> dict:
    """对已合成的 wav 做风格化处理，原地覆盖。

    piper / sapi / openvoice 本身没有角色预设，这里统一用 librosa 改音高与语速：
      萝莉音 = +2 半音 + 语速 1.06；大叔音 = -2 半音 + 语速 0.92；
      播音腔 = ±1~2 半音 + 略慢语速；机械音 = 环形调制 + 24 级量化。
    幅度刻意压小：上一版 ±6 半音会产生明显相位伪影，听感“不对”。
    自然风格直接返回，不做任何 IO。
    """
    style = get_style(style_id)
    if style["id"] == DEFAULT_STYLE:
        return style

    import librosa
    import numpy as np

    data, sr = sf.read(path, dtype="float32")
    if getattr(data, "ndim", 1) > 1:
        data = data.mean(axis=1)
    if style.get("pitch"):
        data = librosa.effects.pitch_shift(data, sr=sr, n_steps=style["pitch"])
    if style.get("tempo") and style["tempo"] != 1.0:
        data = librosa.effects.time_stretch(data, rate=style["tempo"])
    if style.get("robot"):
        data = _robotize(data, sr)

    peak = float(np.abs(data).max() or 1.0)
    if peak > 0.99:
        data = data * (0.99 / peak)
    sf.write(path, data, sr)
    return style


# ----------------------------------------------------------------------
# 各引擎合成
# ----------------------------------------------------------------------
_PIPER_CACHE: dict = {}


def _load_piper(model: str):
    if model in _PIPER_CACHE:
        return _PIPER_CACHE[model]
    from piper import PiperVoice
    voice = PiperVoice.load(os.path.join(VOICE_DIR, f"{model}.onnx"))
    _PIPER_CACHE[model] = voice
    return voice


def _piper_tts(text: str, model: str, out_path: str, speed: float) -> None:
    from piper import SynthesisConfig
    voice = _load_piper(model)
    config = SynthesisConfig(length_scale=round(1.0 / max(speed, 0.5), 3))
    with wave.open(out_path, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=config)


def _sapi_tts(text: str, voice_name: str, out_path: str, speed: float) -> None:
    """用 PowerShell + System.Speech 合成；voice_name 不存在时自动用系统默认。"""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(text)
        text_path = tmp.name
    rate = max(-10, min(10, int((float(speed) - 1.0) * 10)))
    safe_name = voice_name.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"try{{$s.SelectVoice('{safe_name}')}}catch{{}};"
        f"$s.Rate={rate};"
        f"$s.SetOutputToWaveFile('{out_path}');"
        f"$s.Speak([IO.File]::ReadAllText('{text_path}',[Text.Encoding]::UTF8));"
        "$s.Dispose();"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    finally:
        os.unlink(text_path)


def _edge_tts(text: str, model: str, out_path: str, speed: float) -> None:
    """edge-tts 神经网络音色：先落临时 MP3，再解码成 WAV 统一下游读取。

    edge-tts 输出 24kHz MP3（libsndfile ≥1.2 可直接读），本函数把它转成 WAV，
    这样 _meta() / _apply_style() 对所有引擎都用同一套 wav 逻辑。
    """
    import asyncio

    import edge_tts

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".mp3", dir=OUTPUT_DIR)
    os.close(fd)
    rate = f"{int(round((float(speed) - 1.0) * 100)):+d}%"
    try:
        asyncio.run(edge_tts.Communicate(text, model, rate=rate).save(tmp_path))
        data, sr = sf.read(tmp_path, dtype="float32")
        sf.write(out_path, data, sr)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _openvoice_tts(text: str, out_path: str, speed: float, lang: str) -> None:
    """复用 tts.py 的两级流程，但把输出改到独立文件，避免覆盖 advice.wav。"""
    import tts as tts_module
    config = tts_module.load_config() if hasattr(tts_module, "load_config") else None
    if config is None:
        from weather import load_config
        config = load_config()
    local = dict(config)
    local["audio_dir"] = out_path
    local["tmp_audio"] = os.path.join(OUTPUT_DIR, "voice_tmp.wav")
    local["speed"] = speed
    # OpenVoice 基础说话人只支持中/英，其他语言走 piper
    local["language"] = "English" if lang == "en-US" else "Chinese"
    # 试听不写主链路指标文件，避免覆盖 outputs/tts_meta.json
    original_meta = tts_module.META_PATH
    tts_module.META_PATH = os.path.join(OUTPUT_DIR, "voice_openvoice_meta.json")
    try:
        tts_module._openvoice_tts(text, local)
    finally:
        tts_module.META_PATH = original_meta


def _tc3_signature(secret_id: str, secret_key: str, host: str, action: str,
                   payload: str, timestamp: int, service: str = "tts",
                   content_type: str = "application/json; charset=utf-8") -> str:
    """腾讯云 TC3-HMAC-SHA256 签名，返回可直接放进 Authorization 头的字符串。"""
    import hashlib
    import hmac

    date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
    canonical_headers = (f"content-type:{content_type}\n"
                         f"host:{host}\n"
                         f"x-tc-action:{action.lower()}\n")
    signed_headers = "content-type;host;x-tc-action"
    hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = (f"POST\n/\n\n{canonical_headers}\n"
                         f"{signed_headers}\n{hashed_payload}")

    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = (f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n"
                      + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest())

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    secret_date = _hmac(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _hmac(secret_date, service)
    secret_signing = _hmac(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"),
                         hashlib.sha256).hexdigest()
    return (f"TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}")


def _tencent_tts(text: str, lang: str, voice_id: str, out_path: str, speed: float) -> dict:
    """腾讯云 TextToVoice（Version 2019-08-23）：返回 base64 音频，解码后写 wav。

    配置（config.local.yaml 覆盖 config.yaml）：
      provider: tencent
      endpoint: tts.tencentcloudapi.com
      secret_id / secret_key / region
      voice_map: {yue: 粤语音色 VoiceType 数字，如 101019}
    """
    import base64
    import json as json_module
    import time

    import requests

    cloud = load_cloud_config()
    voice_type = (cloud.get("voice_map") or {}).get(lang)
    if not voice_type:
        raise RuntimeError(f"腾讯云 TTS 未配置 {lang} 的 voice_map（控制台查 VoiceType 数字）")
    host = (cloud.get("endpoint") or "tts.tencentcloudapi.com")
    host = host.replace("https://", "").replace("http://", "").split("/")[0]

    payload = {
        "Text": text,
        "SessionId": f"itinerary-{int(time.time())}",
        "ModelType": 1,
        "VoiceType": int(voice_type),
        "Codec": "wav",
        "SampleRate": int(cloud.get("sample_rate", 16000)),
        "Speed": max(-2, min(6, int(round((float(speed) - 1.0) * 5)))),
        "Volume": 0,
        "ProjectId": 0,
        "PrimaryLanguage": 1,
        "EnableSubtitle": False,
    }
    body = json_module.dumps(payload, ensure_ascii=False)
    timestamp = int(time.time())
    headers = {
        "Authorization": _tc3_signature(cloud["secret_id"], cloud["secret_key"],
                                        host, "TextToVoice", body, timestamp),
        "Content-Type": "application/json; charset=utf-8",
        "Host": host,
        "X-TC-Action": "TextToVoice",
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": "2019-08-23",
    }
    if cloud.get("region"):
        headers["X-TC-Region"] = cloud["region"]

    response = requests.post(f"https://{host}", data=body.encode("utf-8"),
                             headers=headers, timeout=30)
    response.raise_for_status()
    result = (response.json() or {}).get("Response") or {}
    error = result.get("Error")
    if error:
        raise RuntimeError(f"腾讯云 {error.get('Code')}: {error.get('Message')}")
    audio = result.get("Audio")
    if not audio:
        raise RuntimeError("腾讯云未返回 Audio 字段")
    raw = base64.b64decode(audio)
    if raw[:4] != b"RIFF":
        raise RuntimeError("腾讯云返回的音频不是 WAV，请把 Codec 设为 wav")
    with open(out_path, "wb") as f:
        f.write(raw)
    return cloud


def _cloud_tts(text: str, lang: str, voice_id: str, out_path: str, speed: float) -> dict:
    """云 TTS 分派：腾讯云走 TC3 签名；其余按通用 HTTP 契约。

    通用约定（便于接入任意云厂商网关）：
      请求  POST {endpoint}  Authorization: Bearer {api_key}
            {"text":..., "lang":..., "voice":..., "speed":..., "format":"wav"}
      响应  Content-Type: audio/*，响应体为音频字节
    """
    import requests

    cloud = load_cloud_config()
    if not cloud_ready():
        raise RuntimeError("云 TTS 未配置：请在 config.local.yaml 填写 cloud_tts.provider / "
                           "endpoint / secret_id / secret_key")
    if cloud.get("provider") == "tencent":
        return _tencent_tts(text, lang, voice_id, out_path, speed)
    payload = {
        "text": text,
        "lang": lang,
        "voice": cloud.get("voice_map", {}).get(lang) or voice_id,
        "speed": speed,
        "format": "wav",
    }
    response = requests.post(
        cloud["endpoint"],
        json=payload,
        headers={"Authorization": f"Bearer {cloud['api_key']}"},
        timeout=30,
    )
    response.raise_for_status()
    content = response.content
    if not (content[:4] == b"RIFF" or content[:3] == b"ID3" or content[:2] == b"\xff\xfb"):
        raise RuntimeError("云 TTS 返回的不是音频数据，请检查 gateway 契约")
    with open(out_path, "wb") as f:
        f.write(content)
    return cloud


def _meta(engine: str, voice: dict, out_path: str, speed: float,
          fallback_reason: str = "", extra: dict | None = None) -> dict:
    info = sf.info(out_path)
    meta = {
        "engine": engine,
        "voice_id": voice["id"],
        "voice_name": voice["name"],
        "lang": voice["lang"],
        "gender": voice["gender"],
        "speed": speed,
        "sample_rate": info.samplerate,
        "duration": round(info.frames / info.samplerate, 2),
        "size_kb": round(os.path.getsize(out_path) / 1024, 1),
        "out_path": out_path,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "fallback_reason": fallback_reason,
    }
    if extra:
        meta.update(extra)
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


def synthesize(text: str, lang: str = "zh-CN", voice_id: str | None = None,
               speed: float = 1.0, out_path: str | None = None,
               allow_fallback: bool = True, style: str = DEFAULT_STYLE) -> dict:
    """按语言/音色/角色风格合成一段语音，返回技术指标。

    style 是角色预设（natural / anchor_f / anchor_m / loli / uncle / robot）。
    未显式指定音色时先按 STYLE_VOICES 换成最贴近该角色的真人神经音色，
    换成功就不再叠加变调（避免上一版 ±6 半音造成的失真）；换不到才用
    _apply_style 做音高/语速处理，保证任意引擎都能出角色效果。
    粤语在云 TTS 未配置时，降级为“普通话音色朗读粤语文本”，
    并在 meta.fallback_reason 中写明，界面同步展示。
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("待合成文本为空")
    if lang not in LANGUAGES:
        raise ValueError(f"不支持的语言：{lang}")

    requested_style = get_style(style)
    style_id = requested_style["id"]
    extra: dict = {}

    if voice_id:
        voice = get_voice(voice_id)
    else:
        voice = None
        mapped = STYLE_VOICES.get(style_id, {}).get(lang)
        if mapped:
            candidate = get_voice(mapped)
            if voice_available(candidate)[0]:
                voice = candidate
                style_id = DEFAULT_STYLE
                extra["style_mode"] = "voice"
        if voice is None:
            voice = get_voice(default_voice(lang))
    if voice["lang"] != lang:
        raise ValueError(f"音色 {voice['id']} 不属于语言 {lang}")

    out_path = out_path or os.path.join(OUTPUT_DIR, f"voice_{voice['id']}.wav")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    ok, reason = voice_available(voice)
    fallback_reason = ""
    if not ok:
        if not allow_fallback:
            raise RuntimeError(f"{voice['name']} 不可用：{reason}")
        fallback_reason = f"{voice['name']} 不可用（{reason}），已用普通话音色代替"
        voice = get_voice("zh-huayan")
        ok, reason = voice_available(voice)
        if not ok:
            raise RuntimeError(f"保底音色也不可用：{reason}")

    engine = voice["engine"]
    if engine == "edge":
        _edge_tts(text, voice["model"], out_path, speed)
    elif engine == "piper":
        _piper_tts(text, voice["model"], out_path, speed)
    elif engine == "sapi":
        _sapi_tts(text, sapi_voice_for(voice["model"]), out_path, speed)
    elif engine == "openvoice":
        _openvoice_tts(text, out_path, speed, lang)
    elif engine == "cloud":
        try:
            extra["provider"] = _cloud_tts(text, lang, voice["id"], out_path, speed).get("provider")
        except Exception as exc:
            if not allow_fallback:
                raise
            fallback_reason = f"云 TTS 调用失败（{exc}），已用普通话音色朗读"
            _piper_tts(text, "zh_CN-huayan-medium", out_path, speed)
            voice = get_voice("zh-huayan")
            engine = "piper"

    # 角色风格最后叠加：换到真人音色时 style_id 已置回 natural，这里只做兜底 DSP
    _apply_style(out_path, style_id)
    extra["style"] = requested_style["id"]
    extra["style_name"] = requested_style["name"]

    return _meta(engine, voice, out_path, speed, fallback_reason, extra)


def check_cloud() -> dict:
    """云 TTS 自检：用当前配置试合成一句粤语，方便填完 Key 立即验证。

    不降级：失败时原样返回错误（腾讯云会给 Code，如 AuthFailure.SignatureFailure），
    便于定位是 Key 写错、未开通服务还是 voice_map 缺少音色编号。
    """
    cloud = load_cloud_config()
    if not cloud_ready():
        return {"ok": False, "provider": cloud.get("provider", ""),
                "reason": "配置不完整：provider/endpoint 为空，"
                          "或 secret_id/secret_key（api_key）仍是占位符"}
    try:
        meta = synthesize(LANGUAGES["yue"]["sample"], "yue", "yue-cloud",
                          out_path=os.path.join(OUTPUT_DIR, "cloud_check.wav"),
                          allow_fallback=False)
    except Exception as exc:
        return {"ok": False, "provider": cloud.get("provider", ""), "reason": str(exc)}
    return {"ok": True, "provider": meta.get("provider", ""),
            "duration": meta["duration"], "out_path": meta["out_path"]}


def audio_url(meta: dict) -> str:
    """把绝对路径映射成 Web 可访问的 /outputs/xxx.wav。"""
    path = meta.get("out_path", "")
    name = os.path.basename(path)
    stamp = meta.get("timestamp", "").replace(":", "").replace("-", "")
    return f"/outputs/{name}?v={stamp}"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="多语言多音色合成")
    parser.add_argument("--lang", default="zh-CN", choices=list(LANGUAGES))
    parser.add_argument("--voice", default=None)
    parser.add_argument("--text", default=None, help="缺省用该语言的示例文案")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--style", default=DEFAULT_STYLE,
                        choices=[row["id"] for row in STYLES],
                        help="角色风格：萝莉音/大叔音/播音腔/机械音等")
    parser.add_argument("--out", default=None)
    parser.add_argument("--list", action="store_true", help="列出语言与音色")
    parser.add_argument("--sapi", action="store_true", help="列出 Windows 已安装的系统语音")
    parser.add_argument("--check-cloud", action="store_true",
                        help="用当前云 TTS 配置试合成一句，打印成功/错误码")
    args = parser.parse_args(argv)

    if args.check_cloud:
        print(json.dumps(check_cloud(), ensure_ascii=False, indent=2))
        return 0

    if args.sapi:
        print(json.dumps(sapi_voices(force=True), ensure_ascii=False, indent=2))
        return 0

    if args.list:
        print(json.dumps(catalog(), ensure_ascii=False, indent=2))
        return 0

    text = args.text or LANGUAGES[args.lang]["sample"]
    meta = synthesize(text, args.lang, args.voice, args.speed, args.out, style=args.style)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
