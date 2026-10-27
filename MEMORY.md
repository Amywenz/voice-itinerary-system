# MEMORY.md — 项目记忆

> 只记“代码里查不到、但下次必须知道”的事实与决策。凭据只记位置不记值。

## 1. 本机环境事实

- `py -0p` 显示默认 3.11：`D:\python311\python.exe`（Python 3.11.0）。系统 `python` 是 3.13.15，缺 requests/pptx，不要用它跑本项目。
- GPU：NVIDIA RTX 4060 Laptop 8GB，驱动 CUDA 12.2；磁盘 F: 剩余约 210GB。
- 网络：pypi / 清华源 / download.pytorch.org / hf-mirror.com / gitee 可访问；github.com 与 huggingface.co 直连超时。
- hf-mirror 可直接下载权重（已核实 200 + Content-Length）：
  - `https://hf-mirror.com/myshell-ai/OpenVoice/resolve/main/checkpoints/converter/checkpoint.pth`（约 131MB）
  - `https://hf-mirror.com/myshell-ai/OpenVoice/resolve/main/checkpoints/base_speakers/ZH/checkpoint.pth`（约 160MB）
- Windows SAPI 已安装中文语音 `Microsoft Huihui Desktop (zh-CN)`，可作为 OpenVoice 权重缺失时的保底合成引擎。
- PowerShell 每次命令都会打印 profile 的 ExecutionPolicy 报错，属宿主环境噪音，不影响命令执行结果。
- 用户附件：PPT 共 64 页（已抽取文本核对）；评审细则覆盖 Rev-A~D 四关。
- 工作区原有 `基于语音生成的行程播报系统需求规格说明书.docx` 与 PPT 要求不一致（写成旅客播报、30 分钟提前量、Android 客户端、Python 3.9），已决定按 PPT + 评分细则重写，原文件保留为历史稿。

## 2. 已确认的设计决策

- 四关全做，目标满分；PPT 是基础要求，额外做 Web 控制台（可视化大屏/仪表盘/课程/天气/语音工坊/设置/日志）作为拓展。
- 语音链路双引擎：优先真实 OpenVoice（CPU/GPU 自适应）；权重缺失时用 Windows SAPI 生成保底音频，并在界面与日志中显式标注引擎，绝不冒充。
- 音色提取不依赖 whisper：对参考音频手工切 3 段（每段 ≤10s），逐段 `ToneColorConverter.extract_se()` 后按样本加权平均，规避 faster-whisper 需联网下载模型的问题；文档里写清切段数。
- 天气接口默认 `provider: mock`（内置离线样例，保证断网/无 key 也能一次跑通演示），配置真实 key 后切 `qweather`；断网时 `fetch_weather_data` 返回 `None`，调用方用 `None` 区分“没网”和“没降水”。
- 提前量固定 10 分钟（评分细则追问点）；`add_course` 用 `OrderedDict` 保证按时间升序。
- 体感温度边界固定 8 与 28：`<8` 保暖、`>28` 防暑、其余适宜；8 与 28 落在“适宜”分支。
- 时间解析统一用 `datetime.fromisoformat()` 兼容 `+08:00` 时区后缀（评分细则 §2.3 第 4 问的标准答案）。
- 真实和风 Key 与专属 API Host 已由用户提供，只写在 `config.local.yaml`（不入提交包）；提交版 `config.yaml` 保持 `YOUR_QWEATHER_KEY` + `provider: mock` + `api_host: devapi.qweather.com`。新版和风 Key 绑定专属域名（形如 `xxxx.qweatherapi.com`），用旧 `devapi` 会返回 403 Invalid Host。
- 周课表与当日课表分离：`data/weekly.json`（`weekday` 1=周一…7=周日）是用户真实课表源，`data/courses.json` 只放当日课程；`Schedule` 三个评分方法签名保持不变，周课表逻辑用 `course.py` 的自由函数 `load_weekly / courses_on / sync_day / today_weekday`，Web 端 `/api/weekly/sync` 按天同步。节次默认时间 08:00 / 10:05 / 13:30 / 15:25 / 18:30（用户确认采用默认作息，学校实际作息待定）。

## 3. 踩坑记录

- python-pptx / python-docx 未安装在 3.13；读 Office 文件用 zipfile + 正则抽 XML 更稳。
- `requests` 未预装；安装依赖前任何联网探测都会 ModuleNotFoundError。
- OpenVoice 官方仓库需要从 GitHub 安装，直连不可用；改用 PyPI 的 `openvoice-cli`（含 openvoice 包）或 hf-mirror 拉 checkpoint。
- OpenVoice 依赖 `numpy<2`，本机 3.11 全局装的是 numpy 2.4.6，必须用独立 `.venv` 隔离。
- simpleaudio 在 Python 3.11 Windows 上需轮子可用；不可用时 play.py 退化为 `winsound.PlaySound`，但保留 simpleaudio 主路径与 `wait_done()`。
- 测试/预览会覆盖交付产物：`tts()` 必须对显式文本 `strip()`（`"   "` 是 truthy，旧的 `if not text` 拦不住）；测试要 monkeypatch `tts.META_PATH`；Web 预览必须传 `output_dir=outputs/preview`；`gene_advice` 必须按 `paths.weather_text` 决定输出目录，否则测试会改写 `resources/weather.txt`。
- 依赖真实时钟的用例在 23:30 后会跨天失败（`now + 30min` 变次日 `00:0x`）：统一用 `datetime` 子类 monkeypatch `now()/today()` 固定时间（如 2026-10-22 09:00），不要用 `pytest.skip` 掩盖。
- 文档里的实测数字（时长/大小/耗时）每次 demo 都会变：改代码后必须重跑 `timer.py --demo`，再同步 SRS/结项/自查表/README/模块记录，并用 `scripts/build_docs.py` 重导 docx。
- 可视化大屏（`/stage`）的天气场景状态类必须写成 `wx-scene--rain/snow/sun/cloud`：早期用 `.wx-cloud` 同时表示“多云状态”和“云朵形状”，后者的绝对定位覆盖了场景容器，导致天空塌成 0 宽。新增组件时状态类与元素类要分前缀。

## 4. 二期扩展（资讯 / 多语言 / 双主题）

- `edge-tts==7.3.1` **在本机可用**（2026-10-23 实测推翻旧结论）：`speech.platform.bing.com:443` 连通，`zh-HK-HiuMaanNeural` 合成 2.9 秒音频约 1 秒完成。输出是 24kHz MP3，本机 libsndfile 1.2.2 可直接 `sf.read`，因此 `_edge_tts()` 走「临时 MP3 → 解码 → 写 WAV」，让 `_meta()`/`_apply_style()` 对所有引擎统一。**默认音色已改为 edge**（各语言第一个音色），Piper 只作断网保底；读 `default_voice()` 的测试不要再假设一定返回 piper。
- Piper 是可行离线方案：`piper-tts==1.8.0` 已装，`PiperVoice.load(path)` + `synthesize_wav(text, wave_file, syn_config=SynthesisConfig(length_scale=...))`；模型放 `voices/`，由 `scripts/download_voices.py` 从 `hf-mirror.com/rhasspy/piper-voices` 下载（zh_CN-huayan / en_US-lessac / en_US-ryan / es_ES-davefx / es_ES-sharvard，共约 315MB，不入库）。
- 多语言试听必须写独立文件 `outputs/voice_<id>.wav` + `outputs/voice_meta.json`，绝不能覆盖 `advice.wav`（评分证据）。OpenVoice 试听时临时改 `tts.META_PATH`，用完还原。
- 云 TTS 两条分支：`provider: tencent` 走腾讯云 `TextToVoice`（自实现 TC3-HMAC-SHA256），其他 provider 走通用 HTTP 契约（POST JSON，响应体直接是音频字节）。`config.local.yaml` 的同名字段覆盖 `config.yaml`；真实 Key 未到位时方言一律降级普通话并写 `fallback_reason`。
- 资讯只用公开 RSS（中国新闻网滚动/社会、人民网时政），无需 Key；缓存 `data/news_cache.json` 30 分钟，全源失败回退过期缓存并置 `stale`。测试通过 autouse fixture 把 `news.fetch_feed` 置空，保证不访问外网。
- `gene_advice(news_items=None)` 时按 `config.yaml` 的 `news.enabled` 自动抓取（`_auto_news()`，异常一律吞掉返回 `[]`），因此定时播报/`timer.py --demo` 也带资讯；Web 显式传入，避免二次抓取。测试配置不写 `news` 段即默认不抓取，用例保持离线可复现。
- 双主题：`html[data-theme="candy"|"cyber"]` + CSS 变量，`theme.css` 在 `style.css` 之后加载；默认 candy（浅色），`localStorage` 键 `itinerary-theme`；首屏内联脚本先应用主题避免闪烁。页面新增 `/news`，接口新增 `/api/news`、`/api/voices`、`/api/voice/tts`。
- 测试规模 46 → 74（新增 TC-43 ~ TC-70）；改完必须同步测试用例表、SRS FR-12~15、SDS §3.4/3.5/§7、结项报告、README，并重导 docx。

## 5. 粤语接入（路线 1：Windows 语音包）

- 已加 `yue-sapi` 音色（`engine=sapi`，`model=zh-HK` 作文化标签），`sapi_voice_for()` 先精确匹配语音名、再按文化前缀匹配；`sapi_voices()` 用 PowerShell System.Speech 取已装语音并进程内缓存，`voices.py --sapi` 可查。
- 本机当前只有 Huihui(zh-CN)、Zira(en-US)，所以 `voice_available` 返回「系统未安装语音「zh-HK」」并降级普通话——这是真实状态，不是 bug。
- 用户装完 Windows「中文(香港特别行政区)」语音包后**必须重启 uvicorn**（语音列表有进程内缓存），再跑 `voices.py --lang yue` 验证；部分 Windows 10 版本只提供 zh-HK 语音识别、不提供 TTS，此时 `--sapi` 不会出现 zh-HK，只能回落到云 TTS。

## 6. 播报控制台（FR-15：地区 / 语言 / 角色 / 快速合成）

- 地区切换贯穿整条链路：`config.yaml` 的 `cities`（15 个城市，带 `name` 字段）→ `/api/trigger`、`/api/weather?city=`、`/api/news?city=` → `gene_advice(city_key=...)`；`weather.MOCK_BY_CITY` 给每个城市不同的离线样例，`news.CITY_KEYWORDS` 一一对应，所以切城市后天气和资讯都会变。
- 角色音色不训练模型：`voices.STYLES`（natural / anchor_f / anchor_m / loli / uncle / robot）先按 `STYLE_VOICES` 换成最贴近的 edge 真人音色（萝莉→晓伊、大叔→云健、播音男→云扬、播音女→晓晓），换成功就跳过 DSP；换不到才用 `_apply_style()` 做 **±1~2 半音** + 语速调整（早期 ±6 半音有明显相位伪影，听感“不对”，已下调），机械音额外做 70Hz 环形调制 + 24 级幅值量化。新增角色改 `STYLES` / `STYLE_VOICES`。
- 速度问题根因是 OpenVoice CPU 推理十几秒。`/api/trigger` 默认 `mode=fast`：`gene_advice(speak=False)` + `voices.synthesize`（默认 edge），实测约 5 秒，写 `outputs/voice_broadcast.wav`；`mode=clone` 才走 OpenVoice，仍写 `advice.wav`。**不要**把 fast 的产物写成 `advice.wav`，那是评分证据。
- 快速播报用 `news.collect(..., cache_only=True)` 只读缓存，避免为 3 条标题等 3 次 RSS 请求；页面切城市时 `/api/weather` 会正常抓取并回填缓存。
- 非中文播报不接翻译接口：`BROADCAST_TEMPLATES` 从「一句话」升级为「分段模板」（intro / temp 三分支 / rain 五分支 / news），`broadcast_text()` 逐句拼；中文仍播 `gene_advice` 的完整建议（含资讯与降水）。2026-10-24 修复「外语播报只有几秒」：外语原来只有 1 句 + 告别语（约 12s），现在补齐当前时间、倒计时（`8 hours and 5 minutes` / `8 horas y 5 minutos` / `8小時5分鐘`）、体感三分支、降水/雨伞、本地资讯入口，实测英 33.6s / 西 33.5s / 粤 30.7s，中文 26.9s。计分与降水判定抽到 `weather.describe_conditions()`，中文建议和外语播报共用 8/28 阈值，避免两套逻辑漂移。另一个坑：英西音色读中文课程名会发音崩掉，`_course_text()` 遇到中文课程名改说 `your next class` / `tu próxima clase`；西语时刻别用 24 小时制（`00:13` 会被逐位读），改 12 小时制。
- 城市跨页面同步（2026-10-23）：`localStorage["itinerary-city"]` 是唯一真源，`app.js` 末尾的 `citySyncModule` 负责读写它、把站内导航链接改写成 `?city=xxx`、用 `BroadcastChannel("itinerary-city")` + `storage` 事件让其他标签页整页跟随；`/stage`、`/weather`、`/news`、`/` 都接收 `city` 参数（`_city_or_default` 校验，非法回退默认城市，但 `/api/news` 对显式非法城市仍返回 400，测试依赖这条）。页面打开时若记忆城市与服务端渲染不一致，先 `location.replace(?city=记忆城市)` 再渲染一次，URL 已有 city 参数所以不会循环。
- `news.collect` 缓存升级为 `{city, updated, items, raw}`：`raw` 是去重后的全量素材（上限 120 条），切城市时用 `filter_items(raw, city)` 本地重排，实测 ~150ms，不再为换城市重抓 3 个 RSS。TTL 仍是 30 分钟，过期才回源。
- 实时刷新节奏：仪表盘 60s 静默拉天气+资讯（只更新 `dash*` id，不弹提示）、天气页 60s、大屏 60s、资讯页 120s 比对 `updated` 变了才 reload；都只在 `document.visibilityState === "visible"` 时跑。
- 「离下节课 0 分钟」的根因：`_next_course` 在当天课全过点后回退到第一节（时间已过），`_normalize_course_time` 又把 `HH:MM` 硬拼到今天 → 差值为负被 `max(...,0)` 夹成 0。修法：`_normalize_course_time` 对过点时间 `+1 day`（课程按天循环），`_next_course` 直接返回次日第一节并把 `datetime` 改到明天；建议文本 ≥60 分钟写成「X小时Y分钟」。`/api/trigger` 的 fast 路径同样按这个规则算 minutes，别再自己 `datetime.combine(today)`。新增 TC-72/TC-73。
- 每日告别语（2026-10-23）：`voices.FAREWELLS` 中文 8 条 / 英西粤各 3 条，`voices.farewell(lang, on=date)` 用 `random.Random(date.toordinal())` 取一条 —— 同一天固定、跨天轮换，可测。中文由 `gene_advice` 在资讯之后拼接并重写 `weather.txt`（因此 CLI/定时/Web clone 都有），外语由 `broadcast_text` 结尾补空格 + 本语言告别语。整段中文播报实测 27.3s（约 30 秒），未加静音填充，也不截断内容。

## 7. 云 TTS 接入（腾讯云，用户主动注册）

- 云 TTS 只做粤语：`config.local.yaml` 填 `cloud_tts.provider: tencent` + `endpoint: tts.tencentcloudapi.com` + `secret_id` / `secret_key` + `voice_map.yue`（VoiceType **数字**）。`config.yaml` 保持占位符。
- 签名不引 SDK：`_tc3_signature()` 用 `hashlib`/`hmac` 实现 TC3-HMAC-SHA256，CanonicalHeaders 固定 `content-type;host;x-tc-action`，签的是 `POST` + `/` + 空 query 的规范请求；`X-TC-Version: 2019-08-23`，Action `TextToVoice`，`Codec=wav`，`SampleRate=16000`。
- 返回体是 `Response.Audio`（base64 WAV）；`Response.Error` 直接抛 `RuntimeError("腾讯云 {Code}: {Message}")`，最容易踩的坑是 SecretId/SecretKey 写反或 `voice_map` 留空。
- 自检命令：`.venv\Scripts\python.exe voices.py --check-cloud`（成功写 `outputs/cloud_check.wav`，失败打印错误码）。粤语三档回退顺序：edge → 本机 SAPI `zh-HK` → 腾讯云。
- 2026-10-23 实际接入结果：腾讯云主账号已建 API 密钥并写入 `config.local.yaml`（`cloud_tts.secret_id/secret_key`，非 git 仓库，无泄露风险）。粤语唯一音色是 **101019 智彤**（官方音色列表 `cloud.tencent.com/document/product/1073/92668`，精品音色，8k/16k）。
- **闽南语已从系统删除**（`voices.py` 的 LANGUAGES / VOICES / 模板、配置、测试、页面、文档全部清理）：腾讯云 TTS 官方只支持中文/英文/粤语，没有任何闽南语音色，edge 与 Piper 也没有。
- 额度问题已解决：先报 `UnsupportedOperation.PkgExhausted`，用户领取免费额度后 `--check-cloud` 返回 `{"ok": true, "duration": 5.1, "out_path": "outputs/cloud_check.wav"}`，腾讯云链路可用。控制台的「语音合成 → 音色列表」入口自动化进不去（/tts/voice 等全 404），查音色编号一律用官方文档表。

## 8. 上线化改造（导航精简 / 待办 / 专注 / 全站音色 / 缓存）

- 导航删除 `/docs`（API 文档）与 `/logs`（播报日志）入口；`/logs` 路由与模板仍保留（数据 `data/runs.jsonl` 供大屏 KPI 统计），只是不对外露出。
- 新增两页：`/todo`（localStorage `itinerary-todos`，跨天自动带入未完成项）、`/focus`（25/5/15 分钟专注 + `itinerary-focus` 统计）。两页逻辑都在 `app.js` 末尾两个 `DOMContentLoaded` 块里，模板只提供元素 id。
- 全站音色：`localStorage["itinerary-voice"]` 存 `{lang,voice,style,name}`，`window.voicePref` + BranchChannel(`itinerary-voice`) + `storage` 事件三路同步；顶栏 `#globalVoice` 徽标展示。`/api/trigger` 的 `TriggerIn.voice` 对应 `voices.synthesize(..., voice_id=...)`，**参数名是 `voice_id` 不是 `voice`**，写错会 500。
- **静态资源必须带版本号**：`templates.env.globals["asset_version"]` 取 `webapp/static` 最新 mtime，模板里写成 `/static/app.js?v={{ asset_version }}`。教训：改了 `app.js` 后浏览器一直命中旧缓存，表现为 `window.todoStore`/`window.voicePref` 为 `undefined`、待办添加“没反应”、音色选了不生效，而服务端文件其实是新的——排查时先确认 `typeof window.todoStore`，不要怀疑代码。
- `setAudio()` 若页面没有 `.js-audio` 会回退 `#latestAudio` 并尝试自动播放；大屏 `stage.html` 的 audio 必须带 `class="js-audio"`，这是“点立即播放没声音”的根因。
- 大屏资讯曾挤在左边：`stage.css` 缺 `.span-12`，`news-card` 只占 1/12 栏；已补 `.span-12` 并把 `.stage-news` 改为 3 栏网格（`theme.css`）。
- 用户要求“日常可用的系统”，界面文案不出现引擎名（edge/Piper/SAPI/OpenVoice）、采样率、链路、权重、Excel/pandas 等；`/api/*` 返回的 `engine` 字段只留在接口里，不再渲染到页面。


