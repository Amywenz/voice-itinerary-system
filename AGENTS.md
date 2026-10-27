# AGENTS.md — 基于语音合成技术的行程播报系统

> 本文件是本项目的协作契约。任何 agent 进入本工作区，先读本文件与 `MEMORY.md`。

## 1. 项目基本信息

| 字段 | 值 |
| --- | --- |
| 项目名 | 基于语音合成技术的行程播报系统（Speech Synthesis Itinerary Broadcast System） |
| 课程 | 《人工智能程序设计》第 4 章 |
| 工作目录 | `f:\pythonmian` |
| 创建日期 | 2026-10-22 |
| 技术栈 | Python 3.11.0 / OpenVoice 预训练模型 / FastAPI + Jinja2 / pytest / PyYAML / simpleaudio |
| 交付关卡 | Rev-A 需求 → Rev-B 设计 → Rev-C 测试 → Rev-D 结项（四关全做） |
| 评分依据 | `基于语音生成的行程播报系统_评审标准细则.md`（用户附件，要求尽量满分） |

## 2. 运行环境约定

- 解释器统一使用 `D:\python311\python.exe`（3.11.0），项目虚拟环境 `.venv`。
- 依赖安装：`D:\python311\python.exe -m venv .venv` 后用 `.venv\Scripts\python.exe -m pip install -r requirements.txt`。
- 所有命令从项目根目录执行；不要在源码里写死绝对路径，路径一律相对项目根。
- 真实 API key 只允许存在于本机 `config.yaml`，仓库内提交的 `config.yaml` 必须是占位符（`YOUR_QWEATHER_KEY`）。
- 提交/交付前清空 `__pycache__`、`outputs/tmp*.wav` 之外的临时产物。
- `checkpoints/` 权重体积大，不进版本库；由 `scripts/download_models.py` 从 hf-mirror 拉取。

## 3. 目录结构（以实际实现为准）

```
course.py          课程表模块：Schedule(add_course/set_timers/show_course)
weather.py         出行建议模块：load_config/get_weather/fetch_weather_data/
                   generate_weather_advice/format_temperature/gene_advice
timer.py           命令行入口：init_course 输入校验 + 定时触发
tts.py             语音合成：BaseSpeakerTTS.tts -> tmp.wav -> ToneColorConverter.convert -> advice.wav
play.py            simpleaudio 播放（wait_done 阻塞）
webapp/            FastAPI 应用、模板、静态资源（拓展页面）
tests/             pytest 用例（正常/边界/异常）
docs/              SRS、SDS、UML 图、结项报告、评审自查表
checkpoints/       OpenVoice 权重（不入库）
resources/         参考音频、weather.txt
outputs/           advice.wav、tmp.wav、运行日志
config.yaml        配置（占位 key）
```

## 4. 评分红线（实现时逐条自检）

1. `python -c "import course, weather, timer"` 必须零报错。
2. `Schedule` 的三个方法名称/参数/返回值必须与类图逐项一致：
   `add_course(self, time, course_name)` / `set_timers(self)` / `show_course(self)`。
3. `course.py`：`OrderedDict` 排序、`timedelta(minutes=10)`、输出 `09:00 - 高等数学`。
4. `weather.py`：双接口字典推导、`raise_for_status` + 异常返回 `None`、体感温度 `<8 / >28 / 其余` 三分支、`'雨'/'雪' in text`。
5. `timer.py`：空输入拦截、`quit` 退出、`strptime("%H:%M")` 校验三条齐备。
6. `tts.py`：必须保留 `tmp.wav` 中间产物，顺序不可颠倒：`BaseSpeakerTTS.tts()` → `ToneColorConverter.convert()`。
7. `outputs/advice.wav` 必须本机生成、可播放、采样率 22050Hz，时长/大小可复述。
8. `gene_advice` 一条命令串联全链路，全程无手工拷贝。
9. pytest 必须使用 `assert`，改动阈值（8/28 → 100）能变红。
10. README 三节齐全：安装 / 运行 / 目录说明，并写清权重来源。
11. 文档闭环：FR 编号 → 类/接口 → 文件/函数 → 测试用例号。
12. 不提交真实 key、无 `__pycache__`、无死代码。

## 5. 代码与文档规范

- 中文注释为主，标识符英文；公共函数写 docstring（中文）。
- 不用过度设计：评分细则没要求的能力不往上堆；每个新增文件必须能指向某条需求或某条评分项。
- 需求/设计/测试文档统一放 `docs/`，用 Markdown 维护源稿，再导出 docx。
- 任何“为什么这样定”的取舍必须写进文档，禁止只写“AI 说应该这样”。
- 修改 `AGENTS.md` / `MEMORY.md` 的结构时，先改文档再改实践。

## 6. 常用命令

```powershell
.venv\Scripts\python.exe -m pytest -q                     # 全量测试
.venv\Scripts\python.exe timer.py                         # 交互录入课程
.venv\Scripts\python.exe timer.py --demo                  # 端到端演示（无人工干预）
.venv\Scripts\python.exe weather.py --advice-only         # 无模型链路：→ weather.txt
.venv\Scripts\python.exe tts.py --text "..."              # 文本 → tmp.wav → advice.wav
.venv\Scripts\python.exe -m uvicorn webapp.main:app --port 8000   # Web 控制台
```
