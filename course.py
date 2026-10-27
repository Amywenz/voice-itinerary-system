"""课程表模块：课程信息存储、按时间排序、课前定时触发。

对应评分细则 B-2 / B-4：
  Schedule.add_course(self, time, course_name)  -> OrderedDict 按 HH:MM 升序
  Schedule.set_timers(self)                    -> 课前 10 分钟触发 gene_advice
  Schedule.show_course(self)                   -> 输出 "09:00 - 高等数学"
"""
from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from datetime import datetime, time as dt_time, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STORAGE = os.path.join(BASE_DIR, "data", "courses.json")
DEFAULT_WEEKLY = os.path.join(BASE_DIR, "data", "weekly.json")
WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


class Schedule:
    """管理课程表，并在每节课开始前 10 分钟调用出行建议模块。"""

    def __init__(self, storage_path: str | None = None):
        # 嵌套字典：time_str -> {'course_name': str, 'time': datetime}
        self.schedule: OrderedDict = OrderedDict()
        self.storage_path = storage_path or DEFAULT_STORAGE
        self._load()

    # ------------------------------------------------------------------
    # 课程增删查
    # ------------------------------------------------------------------
    def add_course(self, time: dt_time, course_name: str) -> str:
        """添加课程并按时间升序排序。

        参数：
            time:        datetime.time 对象，例如 09:00
            course_name: 课程名称，前后空格由调用方或此处去除
        返回：
            格式化后的时间字符串，例如 "09:00"
        """
        course_name = (course_name or "").strip()
        if not course_name:
            raise ValueError("课程名不能为空")
        if not isinstance(time, dt_time):
            raise TypeError("time 必须是 datetime.time 对象")

        today = datetime.today().date()
        course_time = datetime.combine(today, time)
        time_str = course_time.strftime("%H:%M")

        self.schedule[time_str] = {
            "course_name": course_name,
            "time": course_time,
        }
        # OrderedDict 保证遍历顺序即上课顺序，show_course / set_timers 都依赖它
        self.schedule = OrderedDict(sorted(self.schedule.items()))
        self._save()
        return time_str

    def remove_course(self, time_str: str) -> bool:
        """按 HH:MM 删除课程，返回是否删除成功。"""
        if time_str in self.schedule:
            del self.schedule[time_str]
            self._save()
            return True
        return False

    def show_course(self) -> None:
        """按时间顺序打印课程，格式固定为 '09:00 - 高等数学'。"""
        for time_str, course_info in self.schedule.items():
            print(f"{time_str} - {course_info['course_name']}")

    def to_list(self) -> list[dict]:
        """返回课程列表，供 Web 控制台 / 单元测试使用。"""
        return [
            {
                "time": time_str,
                "course_name": info["course_name"],
                "datetime": info["time"].isoformat(timespec="minutes"),
            }
            for time_str, info in self.schedule.items()
        ]

    def clear(self) -> None:
        self.schedule = OrderedDict()
        self._save()

    # ------------------------------------------------------------------
    # 定时触发
    # ------------------------------------------------------------------
    def set_timers(self) -> list[threading.Timer]:
        """为每节课设置定时器，课前 10 分钟调用 gene_advice。

        返回已启动的 Timer 列表，调用方需保持进程存活（timer.py 中阻塞等待）。
        """
        # 延迟导入，避免仅使用课程表时也加载天气/模型依赖
        from weather import gene_advice

        current_time = datetime.now()
        timers: list[threading.Timer] = []

        for time_str, course_info in self.schedule.items():
            course_time = course_info["time"]
            # 提前 10 分钟提醒
            reminder_time = course_time - timedelta(minutes=10)
            delay_seconds = (reminder_time - current_time).total_seconds()

            if delay_seconds > 0:
                timer = threading.Timer(
                    delay_seconds,
                    gene_advice,
                    args=(course_info["course_name"], course_info["time"]),
                )
                timer.daemon = True  # 主线程退出时不留悬挂线程
                timer.start()
                timers.append(timer)
                print(f"[定时] {time_str} {course_info['course_name']}，"
                      f"{delay_seconds / 60:.1f} 分钟后播报")
            else:
                # 已进入课前 10 分钟（或已过点）：立即生成建议，符合 PPT 第 24 页逻辑
                print(f"[立即] {time_str} {course_info['course_name']} 已到提醒时间")
                gene_advice(course_info["course_name"], course_info["time"])

        return timers

    # ------------------------------------------------------------------
    # 持久化（Web 控制台重启后课程不丢）
    # ------------------------------------------------------------------
    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        payload = [
            {"time": time_str, "course_name": info["course_name"]}
            for time_str, info in self.schedule.items()
        ]
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            today = datetime.today().date()
            for item in payload:
                time_str = item["time"]
                hour, minute = map(int, time_str.split(":"))
                self.schedule[time_str] = {
                    "course_name": item["course_name"],
                    "time": datetime.combine(today, dt_time(hour, minute)),
                }
            self.schedule = OrderedDict(sorted(self.schedule.items()))
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            # 存储文件损坏时不阻塞启动，保留空表并在控制台告警
            print(f"[警告] 课程表文件损坏，已忽略：{exc}")
            self.schedule = OrderedDict()


# ----------------------------------------------------------------------
# 周课表：一周多天的课程单独存放，按天同步到 Schedule
# ----------------------------------------------------------------------
def load_weekly(path: str | None = None) -> list[dict]:
    """读取周课表 JSON，返回课程条目列表；文件缺失或损坏时返回空列表。"""
    path = path or DEFAULT_WEEKLY
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[警告] 周课表文件损坏，已忽略：{exc}")
        return []


def courses_on(items: list[dict], weekday: int) -> list[dict]:
    """从周课表中筛出某天的课（weekday：1=周一 … 7=周日），按开始时间升序。"""
    return sorted(
        (item for item in items if item.get("weekday") == weekday),
        key=lambda item: item["start"],
    )


def today_weekday() -> int:
    """今天的星期序号，1=周一 … 7=周日（与周课表口径一致）。"""
    return datetime.today().weekday() + 1


def sync_day(schedule: Schedule, items: list[dict], weekday: int) -> list[dict]:
    """把指定星期的课写入 Schedule（先清空原课程），返回写入的课程条目。"""
    day_courses = courses_on(items, weekday)
    schedule.clear()
    for item in day_courses:
        hour, minute = map(int, item["start"].split(":"))
        schedule.add_course(dt_time(hour, minute), item["course_name"])
    return day_courses


if __name__ == "__main__":
    demo = Schedule()
    demo.show_course()

