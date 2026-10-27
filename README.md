# 基于语音合成技术的行程播报系统

课前 10 分钟自动查询天气、生成出行建议，并用 **OpenVoice** 将文本合成为指定音色的语音播报。附 FastAPI Web 控制台。

- 语音链路：`BaseSpeakerTTS.tts()` → `outputs/tmp.wav` → `ToneColorConverter.convert()` → `outputs/advice.wav`
- 天气链路：和风天气实时天气 + 分钟级降水双接口；无 Key / 断网时使用内置离线样例
- 本地资讯：抓取中国新闻网 / 人民网公开 RSS，按城市关键词筛选后拼进播报文本
- 多语言音色：edge-tts 神经网络音色作默认（普通话 / 英语 / 西班牙语 / 真粤语）+ Piper 离线模型保底 + OpenVoice 克隆 + Windows SAPI；粤语另可用腾讯云 TTS（已接入，101019 智彤）
- 云 TTS：腾讯云 `TextToVoice`（TC3-HMAC-SHA256 签名）已内置，填 SecretId/SecretKey 即可用；未配置时自动降级并写明原因
- 降级策略：权重缺失时切 Windows SAPI，方言云合成未配置时用普通话音色朗读，均在 meta 中标注原因
- Web 控制台：糖果青春 / 赛博校园双主题，一键切换并记忆

## 1. 目录说明

```
course.py            课程表类 Schedule（增删查、排序、持久化、课前 10 分钟定时）
weather.py           配置读取、双天气接口、建议文本生成、全链路编排 gene_advice()
news.py              本地实时资讯：RSS 抓取、城市过滤、30 分钟缓存、播报拼接
voices.py            多语言音色层：语言注册表 + Piper / SAPI / OpenVoice / 云 TTS 适配
timer.py             命令行入口（交互录入 / --demo 端到端演示）
tts.py               OpenVoice 两级合成 + SAPI 降级 + 权重检查
play.py              阻塞播放（simpleaudio.wait_done，降级 winsound）
webapp/              FastAPI 控制台：main.py、templates/、static/
tests/               pytest 用例（正常 / 边界 / 异常，共 74 个执行用例）
docs/                SRS、SDS、测试用例表、模块测试记录、结项报告、评审自查表、UML 图
scripts/             权重下载、音色下载、参考音频生成、UML 绘制、文档导出
checkpoints/         OpenVoice 权重（5 个文件，约 292MB，不入库）
voices/              Piper 音色模型（5 个模型，约 315MB，不入库）
resources/           ly2.wav 参考音频、weather.txt 建议文本
outputs/             tmp.wav、advice.wav、voice_*.wav、tts_meta.json、voice_meta.json
data/                weekly.json 周课表、courses.json 当日课程、runs.jsonl、news_cache.json
config.yaml          配置（提交版本为占位 Key）
```

## 2. 安装

### 2.1 环境要求

- **Python 3.11**（本项目在 3.11.0 验证；3.13 缺少部分依赖，不要用）
- Windows 10/11（SAPI 降级与 `winsound` 播放依赖 Windows；其他系统需替换播放实现）
- 磁盘 ≥ 1GB（权重约 292MB）
- 可选 NVIDIA GPU；无 GPU 时自动用 CPU

### 2.2 创建虚拟环境并安装依赖

```powershell
D:\python311\python.exe -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` 关键版本：`numpy==1.26.4`（OpenVoice 不兼容 numpy 2.x）、`torch==2.1.2`、`torchaudio==2.1.2`、`librosa==0.10.1`、`fastapi`、`uvicorn`、`pytest`、`python-docx`。

### 2.3 下载 OpenVoice 权重

权重来源：HuggingFace 仓库 `myshell-ai/OpenVoice`，国内使用镜像 `hf-mirror.com`。

```powershell
.venv\Scripts\python.exe scripts\download_models.py
```

会下载 5 个文件到 `checkpoints/`：

```
checkpoints/base_speakers/ZH/config.json
checkpoints/base_speakers/ZH/checkpoint.pth          (约 160MB)
checkpoints/base_speakers/ZH/zh_default_se.pth
checkpoints/converter/config.json
checkpoints/converter/checkpoint.pth                  (约 131MB)
```

检查是否齐全：

```powershell
.venv\Scripts\python.exe tts.py --status
```

### 2.4 准备参考音频

仓库已包含 `resources/ly2.wav`（30.93 秒中文语音，作为目标音色）。如需重新生成：

```powershell
.venv\Scripts\python.exe scripts\make_reference.py
```

脚本使用 Windows SAPI `Microsoft Huihui Desktop` 合成，再重采样到 22050Hz。

### 2.5 多语言音色（可选）

**默认引擎是 edge-tts 神经网络音色**（`pip install edge-tts`，已写入 requirements），零 Key、需联网，音质明显好于 Piper。普通话用晓晓/云希等，粤语用 `zh-HK-HiuMaanNeural`（真粤语），断网时自动回退下列离线模型。

普通话 / 英语 / 西班牙语的离线保底使用 Piper 模型，来源 `rhasspy/piper-voices`（HuggingFace 镜像 `hf-mirror.com`）：

```powershell
.venv\Scripts\python.exe scripts\download_voices.py
.venv\Scripts\python.exe scripts\download_voices.py --list   # 只看状态
```

会下载 5 个模型到 `voices/`（约 315MB）：

```
voices/zh_CN-huayan-medium.onnx       (+ .onnx.json)   普通话女声
voices/en_US-lessac-medium.onnx       (+ .onnx.json)   英语女声
voices/en_US-ryan-medium.onnx         (+ .onnx.json)   英语男声
voices/es_ES-davefx-medium.onnx       (+ .onnx.json)   西语男声
voices/es_ES-sharvard-medium.onnx     (+ .onnx.json)   西语女声
```

闽南语已移除：腾讯云 TTS 官方只支持中文 / 英文 / 粤语，没有闽南语音色，因此系统不再提供该语言。粤语的云 TTS 备份在 `config.local.yaml` 填 `cloud_tts`（`provider: tencent` + SecretId/SecretKey + `voice_map.yue` 的 VoiceType 数字，当前为 101019 智彤），然后 `voices.py --check-cloud` 自检。未配置时系统会用普通话音色朗读粤语文本，并在界面与 `outputs/voice_meta.json` 写明降级原因。

### 2.6 配置 `config.yaml`

```yaml
api_key: "YOUR_QWEATHER_KEY"   # 填真实和风天气 Key
provider: mock                 # mock 离线样例 / qweather 真实接口
api_host: "devapi.qweather.com"  # 新版账号填控制台分配的 xxxx.qweatherapi.com
default_city: dalian
```

- 保持占位符 → 自动使用离线样例，断网也能演示；
- 填真实 Key、把 `provider` 改为 `qweather`，并按账号填 `api_host` → 请求真实接口；
- 本机真实 Key 放在 `config.local.yaml`，用 `--config config.local.yaml` 运行；提交版 `config.yaml` 始终保留占位符。
- **不要提交真实 Key**（评分红牌）。

## 3. 运行

### 3.1 端到端演示（一条命令，无人工干预）

```powershell
.venv\Scripts\python.exe timer.py --demo
```

流程：读配置 → 查天气 →（`news.enabled: true` 时抓取本地资讯）→ 生成建议 → 写 `resources/weather.txt` → 两级合成 → 播放。本机 CPU 首次运行约 40 秒（含加载权重与约 19 秒音频）。断网时资讯自动跳过，不影响播报。

### 3.2 交互式录入课程

```powershell
.venv\Scripts\python.exe timer.py
```

输入课程名与 `HH:MM` 时间；输入 `quit` 退出并显示课程表；随后按课前 10 分钟设置定时器。

### 3.3 只跑无模型链路

```powershell
.venv\Scripts\python.exe weather.py --advice-only
```

只生成 `resources/weather.txt`，不加载 torch/OpenVoice。用于先验证配置与天气解析。

### 3.4 单独合成语音

```powershell
.venv\Scripts\python.exe tts.py --text "测试文本"
.venv\Scripts\python.exe tts.py --engine sapi --text "测试文本"
.venv\Scripts\python.exe play.py outputs\advice.wav
```

### 3.5 Web 控制台

```powershell
.venv\Scripts\python.exe -m uvicorn webapp.main:app --port 8000
```

打开 <http://127.0.0.1:8000>。页面：仪表盘 `/`、可视化大屏 `/stage`、课程 `/courses`、天气 `/weather`、今日资讯 `/news`、语音工坊 `/studio`、设置 `/settings`、日志 `/logs`；接口文档 `/docs`。

顶栏右上角可切换 **糖果青春（浅色）** 与 **赛博校园（深色）** 两套主题，选择保存在浏览器 localStorage。

仪表盘顶部是「播报控制台」：**地区**（内置 15 个城市，含大连、北京、上海、广州、成都等）、**语言**（普通话 / 英语 / 西班牙语 / 粤语）、**音色角色**（自然、播音腔女声、播音腔男声、萝莉音、大叔音、机械音）、**播报方式**（快速合成约 5 秒 / OpenVoice 音色克隆）。切地区会同时刷新天气与本地资讯；快速播报写入 `outputs/voice_broadcast.wav`，不覆盖交付证据 `advice.wav`。
语音工坊的「多语言音色实验室」可以切换 4 种语言（普通话 / 英语 / 西班牙语 / 粤语）、逐个音色试听，并叠加同一套角色风格；试听写入 `outputs/voice_<id>.wav`。

课程页顶部是 `data/weekly.json` 里的周课表（周一至周五），点「载入今天的课」会把当天课程同步为 `data/courses.json`，仪表盘与大屏随即按真实课程计算课前 10 分钟倒计时。节次时间默认按 08:00 / 10:05 / 13:30 / 15:25 / 18:30 起算，可直接改 `weekly.json` 的 `start`、`end` 字段调整。

### 3.6 多语言 / 某地资讯（命令行）

```powershell
.venv\Scripts\python.exe news.py --city dalian --limit 5 --force   # 抓取并打印本地资讯
.venv\Scripts\python.exe voices.py --list                           # 语言与音色清单
.venv\Scripts\python.exe voices.py --lang es-ES --voice es-dave     # 西语试听
.venv\Scripts\python.exe voices.py --sapi                               # 查看已安装的系统语音（含粤语 zh-HK）
.venv\Scripts\python.exe voices.py --lang yue                            # 粤语（默认 edge 曉曼，断网时降级）
.venv\Scripts\python.exe voices.py --check-cloud                         # 云 TTS 自检（填完腾讯云 Key 后跑）
```

### 3.7 测试

```powershell
.venv\Scripts\python.exe -m pytest -q
```

预期：`74 passed`，约 6 秒。

## 4. 引擎说明

| 引擎 | 触发条件 | 产物 | 标注 |
| --- | --- | --- | --- |
| OpenVoice | 5 个权重与参考音频存在，`tts_engine=auto/openvoice` | `tmp.wav` + `advice.wav`（22050Hz） | `engine=openvoice` |
| Windows SAPI | 权重缺失 / 推理失败且 `auto`；或显式 `engine=sapi` | `tmp.wav` + `advice.wav`（重采样 22050Hz） | `engine=sapi` + `fallback_reason` |
| edge-tts 神经音色 | 已装 `edge-tts` 且能联网（默认） | `outputs/voice_<id>.wav`（24kHz） | `engine=edge` |
| Piper | edge 不可用，或显式选 piper 音色 | `outputs/voice_<id>.wav`（22050Hz） | `engine=piper` |
| Windows SAPI 方言 | 装了「中文(香港)」语音包，粤语音色命中 zh-HK | `outputs/voice_yue.wav` | `engine=sapi`、`lang=yue` |
| 腾讯云 TTS | 方言音色且 `cloud_tts.provider=tencent`、Key 有效 | `outputs/voice_<id>.wav` | `engine=cloud`、`provider=tencent`；失败时降级 `piper` + 原因 |

播放优先 `simpleaudio`；本机无 MSVC 装不上时自动降级 `winsound`（同步阻塞，语义等价 `wait_done`）。

## 5. 常见问题

| 问题 | 处理 |
| --- | --- |
| `ModuleNotFoundError: requests` | 用了系统 Python 3.13；改用 `.venv\Scripts\python.exe` |
| 权重下载超时 | 确认可访问 `hf-mirror.com`；脚本已带 3 次重试 |
| `simpleaudio` 安装失败 | 无需处理，`play.py` 会自动降级 `winsound` |
| 没有声音 | 检查 `outputs/advice.wav` 是否存在；执行 `python play.py outputs/advice.wav` 单独验证 |
| 天气始终是 mock | `config.yaml` 的 `api_key` 仍是占位符，或 `provider` 不是 `qweather` |
| 音色显示「需配置」 | 普通话/英/西/粤语默认走 edge-tts，装好 `edge-tts` 且能联网即可；离线时跑 `scripts\download_voices.py` 用 Piper 保底；粤语云合成需腾讯云 `cloud_tts` 与有效资源包 |
| 资讯页面为空 | 外网 RSS 不可达；系统会读 `data/news_cache.json` 的旧缓存并标注「离线缓存」 |
| CPU 合成慢 | 正常；模型只加载一次，建议播报文本控制在 120 字内 |

## 6. 文档索引

- [需求规格说明书](docs/SRS.md)
- [概要设计说明书](docs/SDS.md)
- [测试用例表](docs/测试用例表.md)
- [模块测试记录](docs/模块测试记录.md)
- [结项报告](docs/结项报告.md)
- [评审自查表](docs/评审自查表.md)
- [用例图](docs/uml/use_case.png) / [类图](docs/uml/class_diagram.png) / [时序图](docs/uml/sequence.png)
