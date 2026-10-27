"""生成 SRS/SDS 所需的 UML 图（用例图、类图、时序图）。

不依赖 Graphviz，使用 matplotlib 直接绘制，输出 PNG（220dpi）与 SVG。
用法：python scripts/make_diagrams.py
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, FancyBboxPatch, Rectangle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "uml")
os.makedirs(OUT_DIR, exist_ok=True)

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"
FONT = FontProperties(fname=FONT_PATH if os.path.exists(FONT_PATH) else None)
plt.rcParams["axes.unicode_minus"] = False

INK = "#1f2937"
ACCENT = "#0f766e"
SOFT = "#ecfdf5"
BLUE = "#e0f2fe"
GRAY = "#f8fafc"
YELLOW = "#fefce8"
LINE = "#475569"
AMBER = "#b45309"


def new_canvas(width: float, height: float):
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(0, width * 10)
    ax.set_ylim(0, height * 10)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    return fig, ax


def text(ax, x, y, value, size=10, color=INK, weight="normal", ha="center", va="center"):
    ax.text(x, y, value, fontproperties=FONT, fontsize=size, color=color,
            fontweight=weight, ha=ha, va=va, linespacing=1.55)


def actor(ax, x, y, label):
    """标准 UML 参与者：圆头 + 躯干 + 四肢，坐标按 1 单位≈0.1 英寸设计。"""
    ax.add_patch(Circle((x, y + 9.5), 2.0, fill=False, ec=LINE, lw=1.6))
    ax.plot([x, x], [y + 7.5, y + 2.4], color=LINE, lw=1.6)
    ax.plot([x - 3.2, x + 3.2], [y + 5.8, y + 5.8], color=LINE, lw=1.6)
    ax.plot([x, x - 2.6], [y + 2.4, y - 1.8], color=LINE, lw=1.6)
    ax.plot([x, x + 2.6], [y + 2.4, y - 1.8], color=LINE, lw=1.6)
    text(ax, x, y - 4.2, label, size=10.5, weight="bold")


def usecase(ax, x, y, label, w=34, h=11, fill=SOFT):
    ax.add_patch(Ellipse((x, y), w, h, fc=fill, ec=ACCENT, lw=1.5))
    text(ax, x, y, label, size=9.5)


def box(ax, x, y, w, h, title, lines, fill=GRAY, title_color=ACCENT, line_size=9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.03,rounding_size=0.25",
                                fc=fill, ec=LINE, lw=1.3))
    ax.plot([x, x + w], [y + h - 3.2, y + h - 3.2], color=LINE, lw=1.1)
    text(ax, x + w / 2, y + h - 1.6, title, size=10.5, weight="bold", color=title_color)
    for index, line in enumerate(lines):
        text(ax, x + 0.8, y + h - 4.4 - index * 2.15, line, size=line_size, ha="left")


def arrow(ax, start, end, style="-|>", dashed=False, label=None, rad=0.0,
          color=LINE, label_pos="mid", label_offset=(0, 0), lw=1.4, size=8):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle=style, mutation_scale=13,
        lw=lw, color=color, linestyle="--" if dashed else "-",
        connectionstyle=f"arc3,rad={rad}", shrinkA=4, shrinkB=4,
    ))
    if not label:
        return
    if label_pos == "mid":
        x, y = (start[0] + end[0]) / 2 + label_offset[0], (start[1] + end[1]) / 2 + label_offset[1]
        text(ax, x, y, label, size=size, color=color)
    elif label_pos == "right":
        text(ax, max(start[0], end[0]) + 1.2, (start[1] + end[1]) / 2 + label_offset[1],
             label, size=size, color=color, ha="left")
    elif label_pos == "left":
        text(ax, min(start[0], end[0]) - 1.2, (start[1] + end[1]) / 2 + label_offset[1],
             label, size=size, color=color, ha="right")


def save(fig, name):
    for ext in ("png", "svg"):
        fig.savefig(os.path.join(OUT_DIR, f"{name}.{ext}"), dpi=220,
                    bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ----------------------------------------------------------------------
# 1. 用例图：4 个主用例 + 2 条异常流
# ----------------------------------------------------------------------
def draw_use_case():
    fig, ax = new_canvas(16, 10.4)
    ax.add_patch(Rectangle((34, 7), 118, 87, fc="white", ec=LINE, lw=1.4, ls="--"))
    text(ax, 93, 90.5, "行程播报系统", size=13, weight="bold", color=ACCENT)

    # 参与者全部放在左侧，避免与右侧异常/子用例的箭头交叉
    actor(ax, 12, 89, "学生 / 管理员")
    actor(ax, 12, 62, "系统时钟")
    actor(ax, 12, 40, "和风天气 API")
    actor(ax, 12, 15, "扬声器")

    # 4 个主用例：名称与任务清单逐字一致
    usecase(ax, 68, 84, "录入课程", w=34)
    usecase(ax, 68, 66, "定时触发", w=34)
    usecase(ax, 68, 48, "查询天气", w=34)
    usecase(ax, 68, 30, "语音播报", w=34)

    # 子用例与异常用例
    usecase(ax, 118, 84, "输入校验", w=38, fill=BLUE)
    usecase(ax, 118, 66, "无课程提示", w=38, fill=BLUE)
    usecase(ax, 118, 48, "生成出行建议", w=40)
    usecase(ax, 118, 38, "断网降级", w=36, h=10, fill=BLUE)
    usecase(ax, 118, 28, "音色转换", w=34, h=10)
    usecase(ax, 118, 16, "权重缺失降级 SAPI", w=44, h=10, fill=BLUE)

    # 参与者关联（实线）
    arrow(ax, (14.5, 89), (50.5, 84), style="-", rad=0.04)
    arrow(ax, (14.5, 89), (50.5, 67), style="-", rad=0.02)
    arrow(ax, (14.5, 62), (50.5, 67), style="-", rad=0.02)
    arrow(ax, (14.5, 40), (50.5, 48), style="-", rad=0.02)
    arrow(ax, (14.5, 15), (50.5, 29), style="-", rad=-0.06)

    # include：父用例 → 必须经过的子用例（虚线，指向子用例）
    arrow(ax, (86, 48), (97, 48), dashed=True, label="«include»", label_pos="mid",
          label_offset=(0, 1.3))
    arrow(ax, (86, 30), (97, 28.5), dashed=True, label="«include»", label_pos="mid",
          label_offset=(0, 1.3))

    # extend：异常/降级用例 → 被扩展的主用例（虚线，指向主用例）
    arrow(ax, (98, 84), (86, 84), dashed=True, color=AMBER, label="«extend»",
          label_pos="mid", label_offset=(0, 1.4))
    arrow(ax, (98, 66), (86, 66), dashed=True, color=AMBER, label="«extend»",
          label_pos="mid", label_offset=(0, 1.4))
    arrow(ax, (98, 37), (86, 45), dashed=True, color=AMBER, label="«extend»",
          label_pos="mid", label_offset=(0, 0.9))
    arrow(ax, (98, 15), (86, 27), dashed=True, color=AMBER, label="«extend»",
          label_pos="mid", label_offset=(0, -1.2))

    text(ax, 35, 4.6, "说明：«include» 表示必须经过的子用例；«extend» 表示异常/降级分支，"
                      "覆盖空输入、无课程、断网、权重缺失四类场景。",
         size=8.6, color=LINE, ha="left")
    text(ax, 35, 1.4, "参与者：学生/管理员、系统时钟、和风天气 API、扬声器",
         size=8.6, color=LINE, ha="left")
    save(fig, "use_case")


# ----------------------------------------------------------------------
# 2. 类图：1 个业务类 + 5 个模块
# ----------------------------------------------------------------------
def draw_class():
    fig, ax = new_canvas(16, 10)
    text(ax, 80, 96, "行程播报系统 · 类图（类与模块职责）", size=14, weight="bold")

    box(ax, 3, 38, 46, 42, "Schedule", [
        "- schedule: OrderedDict",
        "- storage_path: str",
        "+ add_course(time, course_name): str",
        "+ remove_course(time_str): bool",
        "+ show_course(): None",
        "+ set_timers(): list[Timer]",
        "+ to_list(): list[dict]",
        "+ clear(): None",
        "- _save(): None",
        "- _load(): None",
    ], line_size=9.2)
    text(ax, 3.5, 34, "course.py", size=9, color=LINE, ha="left")

    box(ax, 56, 64, 46, 24, "«module» weather.py", [
        "+ load_config(filename)",
        "+ fetch_weather_data(url): dict|None",
        "+ get_weather(api_key, city, location)",
        "+ generate_weather_advice(...)",
        "+ gene_advice(course, ct, ...)",
    ], fill="#eff6ff", line_size=8.8)
    box(ax, 108, 64, 48, 24, "«module» tts.py", [
        "+ tts(config, text, engine)",
        "+ check_weights()",
        "- _openvoice_tts(text, config)",
        "- _sapi_tts(text, config)",
        "- _extract_target_se(...)",
    ], fill="#f0fdfa", line_size=8.8)
    box(ax, 110, 34, 46, 18, "«module» play.py", [
        "+ play_audio(audio_path): bool",
        "  simpleaudio.wait_done() 阻塞",
        "  不可用时降级 winsound",
    ], fill=YELLOW, line_size=8.8)
    box(ax, 56, 34, 46, 20, "«module» timer.py", [
        "+ init_course(schedule): None",
        "+ main(argv): int",
        "  空输入 / quit / 时间格式校验",
    ], line_size=8.8)
    box(ax, 56, 5, 46, 20, "«module» webapp/main.py", [
        "  FastAPI 路由（6 个页面）",
        "  /api/courses  /api/trigger",
        "  /api/tts  /api/config  /api/logs",
    ], fill="#f5f3ff", line_size=8.8)

    arrow(ax, (49, 59), (56, 72), label="gene_advice()", label_pos="right", rad=0.08)
    arrow(ax, (102, 76), (110, 76), label="调用", label_pos="right")
    arrow(ax, (79, 54), (79, 64), label="调度", label_pos="right")
    arrow(ax, (133, 64), (133, 52), label="播放", label_pos="right")
    arrow(ax, (79, 25), (79, 34), label="复用", label_pos="right")

    text(ax, 56, 2.2, "说明：系统只有 1 个业务类 Schedule，天气/语音/播放按模块函数组织；"
                      "类图与代码逐项对应，未虚构类。",
         size=8.6, color=LINE, ha="left")
    save(fig, "class_diagram")


# ----------------------------------------------------------------------
# 3. 时序图：课前 10 分钟自动播报
# ----------------------------------------------------------------------
def draw_sequence():
    fig, ax = new_canvas(18, 10.6)
    text(ax, 90, 100, "行程播报系统 · 时序图（课前 10 分钟自动播报）", size=14, weight="bold")

    lanes = [
        ("学生", 10), ("timer.py", 34), ("Schedule", 58), ("weather.py", 82),
        ("天气 API", 108), ("tts.py", 130), ("OpenVoice", 152), ("play.py", 172),
    ]
    top, bottom = 92, 8
    for label, x in lanes:
        ax.add_patch(FancyBboxPatch((x - 7, top - 4), 14, 5,
                                    boxstyle="round,pad=0.02,rounding_size=0.15",
                                    fc="#e2e8f0", ec=LINE, lw=1.1))
        text(ax, x, top - 1.5, label, size=9.5, weight="bold")
        ax.plot([x, x], [top - 4, bottom], color="#94a3b8", lw=1, ls="--")

    steps = [
        (0, 1, "输入课程名 / 时间", "solid"),
        (1, 2, "add_course(time, course_name)", "solid"),
        (2, 1, "写入 OrderedDict 并排序", "dashed"),
        (1, 2, "set_timers()", "solid"),
        (2, 1, "Timer(课前 10 分钟)", "dashed"),
        (2, 3, "gene_advice(course, time)", "solid"),
        (3, 3, "load_config()", "self"),
        (3, 4, "get_weather(key, city, location)", "solid"),
        (4, 3, "JSON / None", "dashed"),
        (3, 3, "生成建议 → weather.txt", "self"),
        (3, 5, "tts(config)", "solid"),
        (5, 6, "BaseSpeakerTTS.tts() → tmp.wav", "solid"),
        (5, 6, "ToneColorConverter.convert() → advice.wav", "solid"),
        (5, 3, "返回 tts_meta", "dashed"),
        (3, 7, "play_audio(advice.wav)", "solid"),
        (7, 7, "wait_done() 阻塞", "self"),
        (7, 0, "播报完成", "dashed"),
    ]

    y = top - 8
    for index, (src, dst, label, kind) in enumerate(steps, start=1):
        x1, x2 = lanes[src][1], lanes[dst][1]
        if kind == "self":
            ax.plot([x1, x1 + 5, x1 + 5, x1], [y, y, y - 2.0, y - 2.0], color=LINE, lw=1.2)
            ax.add_patch(FancyArrowPatch((x1 + 5, y - 2.0), (x1 + 0.2, y - 2.0),
                                         arrowstyle="-|>", mutation_scale=10, color=LINE))
            text(ax, x1 + 6.2, y - 1.0, f"{index}. {label}", size=8.4, ha="left")
        else:
            dashed = kind == "dashed"
            ax.add_patch(FancyArrowPatch((x1, y), (x2, y), arrowstyle="-|>",
                                         mutation_scale=11, lw=1.3, color=LINE,
                                         linestyle="--" if dashed else "-"))
            text(ax, min(x1, x2) + 1.6, y + 1.05, f"{index}. {label}", size=8.4, ha="left")
        y -= 4.5

    ax.add_patch(FancyBboxPatch((5, 4), 120, 3.6, boxstyle="round,pad=0.05,rounding_size=0.2",
                                fc="#fffbeb", ec=AMBER, lw=1.0))
    text(ax, 8, 5.8, "异常分支：断网 → 播报降级文案；权重缺失 → 自动改用 SAPI，并在 tts_meta.json 标注 engine=sapi",
         size=8.2, color="#92400e", ha="left")
    save(fig, "sequence")


if __name__ == "__main__":
    draw_use_case()
    draw_class()
    draw_sequence()
    print(f"已生成 UML 图：{OUT_DIR}")
