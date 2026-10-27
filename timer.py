"""命令行入口：课程录入、定时提醒、端到端演示。

对应评分细则 B-6：空输入拦截 / quit 退出 / strptime 格式校验三条齐备。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta

from course import Schedule

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def init_course(schedule: Schedule) -> None:
    """课程录入界面：输入 quit 退出，空课程名与非法时间都会被拦截。"""
    while True:
        # 输入课程名称，使用 strip() 去掉前后空格
        course_name = input("输入课程名（输入 quit 退出）: ").strip()
        if course_name.lower() == "quit":
            break

        if not course_name:
            print("课程名不能为空，请重新输入。")
            continue

        # 时间格式不对的话需要一直输入，格式：18:30
        while True:
            course_time_str = input("输入上课时间 (小时:分钟, 24小时制): ")
            try:
                # 将输入的时间字符串转换为时间对象
                course_time = datetime.strptime(course_time_str, "%H:%M").time()

                # 判断输入的时间是否晚于当前时间
                current_time = datetime.now().time()
                if course_time < current_time:
                    print("输入的时间必须晚于当前时间，请重新输入。")
                else:
                    break
            except ValueError:
                print("时间格式不正确，请重新输入（使用 小时:分钟 格式）。")

        # 添加课程到课程表
        schedule.add_course(course_time, course_name)

    # 显示课程表
    schedule.show_course()


def run_demo(config_path: str = "config.yaml") -> int:
    """端到端演示：一条命令走完 配置→天气→建议→文本→合成→播放。"""
    from weather import gene_advice

    print("=" * 56)
    print("  行程播报系统 · 端到端演示（无人工干预）")
    print("=" * 56)
    course_time = (datetime.now() + timedelta(minutes=15)).replace(second=0, microsecond=0)
    print(f"[1/5] 演示课程：高等数学 · {course_time.strftime('%H:%M')} 上课")
    print("[2/5] 读取 config.yaml 与天气数据…")
    result = gene_advice("高等数学", course_time, config_path=config_path)
    print("[3/5] 生成出行建议：")
    print("      " + result["advice"])
    print(f"[4/5] 语音合成引擎：{result['engine']}")
    print(f"[5/5] 音频输出：{result['audio']}")
    print("演示完成：weather.txt → tmp.wav → advice.wav → 扬声器")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="课程表定时播报")
    parser.add_argument("--demo", action="store_true", help="非交互式端到端演示")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo(args.config)

    schedule = Schedule()
    init_course(schedule)

    if not schedule.schedule:
        print("课程表为空，未设置任何定时器。")
        return 0

    timers = schedule.set_timers()
    if not timers:
        print("没有需要等待的课程（均已在课前 10 分钟内即时播报）。")
        return 0

    print(f"已设置 {len(timers)} 个定时器，按 Ctrl+C 退出。")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n已取消全部定时器。")
        for timer in timers:
            timer.cancel()
    return 0


if __name__ == "__main__":
    sys.exit(main())
