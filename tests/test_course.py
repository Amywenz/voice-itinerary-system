"""课程表模块测试：排序、输出格式、10 分钟定时、异常输入。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

import course as course_module
from course import Schedule


def make_schedule(tmp_path) -> Schedule:
    return Schedule(str(tmp_path / "courses.json"))


def test_add_course_sorted_and_show(tmp_path, capsys):
    """FR-01：乱序录入后按 HH:MM 升序，show_course 输出固定格式。"""
    schedule = make_schedule(tmp_path)
    schedule.add_course(datetime.strptime("10:00", "%H:%M").time(), "大学物理")
    schedule.add_course(datetime.strptime("08:30", "%H:%M").time(), "高等数学")
    schedule.add_course(datetime.strptime("09:15", "%H:%M").time(), "线性代数")

    assert list(schedule.schedule.keys()) == ["08:30", "09:15", "10:00"]

    schedule.show_course()
    output = capsys.readouterr().out
    assert "08:30 - 高等数学" in output
    assert output.index("08:30") < output.index("09:15") < output.index("10:00")


def test_add_course_rejects_empty_name(tmp_path):
    """异常用例：空课程名必须抛 ValueError，不能写进课程表。"""
    schedule = make_schedule(tmp_path)
    with pytest.raises(ValueError):
        schedule.add_course(datetime.strptime("09:00", "%H:%M").time(), "   ")
    assert len(schedule.schedule) == 0


def test_set_timers_uses_ten_minutes(tmp_path, monkeypatch):
    """FR-02：定时器延迟 = 上课时间 - 当前时间 - 10 分钟。"""
    # 固定当前时间为 09:00，避免用例在午夜附近跨天失效
    fixed_now = datetime(2026, 10, 22, 9, 0, 0)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

        @classmethod
        def today(cls):
            return fixed_now

    monkeypatch.setattr(course_module, "datetime", FixedDateTime)

    schedule = make_schedule(tmp_path)
    course_time = fixed_now + timedelta(minutes=30)
    schedule.add_course(course_time.time(), "数据结构")

    created = []

    # 防止误触发真实播报；保留函数名以便断言定时器目标
    def gene_advice(*args, **kwargs):
        return None

    monkeypatch.setattr("weather.gene_advice", gene_advice)

    class FakeTimer:
        def __init__(self, delay, func, args=()):
            self.delay = delay
            self.func = func
            self.args = args
            self.started = False
            created.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.started = False

    monkeypatch.setattr(course_module.threading, "Timer", FakeTimer)
    timers = schedule.set_timers()

    assert len(timers) == 1
    assert timers[0].started is True
    # 09:30 上课，09:00 现在，提前 10 分钟 → 延迟 20 分钟 = 1200 秒
    assert timers[0].delay == 1200
    assert timers[0].func.__name__ == "gene_advice"


def test_set_timers_triggers_immediately_when_inside_window(tmp_path, monkeypatch):
    """边界：已进入课前 10 分钟时立即播报，而不是等待负数延迟。"""
    schedule = make_schedule(tmp_path)
    course_time = datetime.now() + timedelta(minutes=5)
    schedule.add_course(course_time.time(), "英语")

    calls = []
    monkeypatch.setattr("weather.gene_advice", lambda c, t, **kw: calls.append((c, t)))

    timers = schedule.set_timers()
    assert timers == []
    assert len(calls) == 1
    assert calls[0][0] == "英语"


def test_persistence_roundtrip(tmp_path):
    """FR-06：课程写入 JSON 后重新加载仍按时间排序。"""
    path = str(tmp_path / "courses.json")
    first = Schedule(path)
    first.add_course(datetime.strptime("14:00", "%H:%M").time(), "操作系统")
    first.add_course(datetime.strptime("09:00", "%H:%M").time(), "高数")

    second = Schedule(path)
    assert list(second.schedule.keys()) == ["09:00", "14:00"]
    assert second.schedule["09:00"]["course_name"] == "高数"


def test_remove_course(tmp_path):
    schedule = make_schedule(tmp_path)
    schedule.add_course(datetime.strptime("09:00", "%H:%M").time(), "高数")
    assert schedule.remove_course("09:00") is True
    assert schedule.remove_course("09:00") is False
    assert len(schedule.schedule) == 0


def test_weekly_load_and_filter(tmp_path):
    """周课表：按星期筛选并按开始时间升序，缺失文件返回空列表。"""
    path = tmp_path / "weekly.json"
    path.write_text(json.dumps([
        {"weekday": 1, "start": "13:30", "end": "15:05", "course_name": "英语"},
        {"weekday": 1, "start": "08:00", "end": "09:35", "course_name": "高数"},
        {"weekday": 2, "start": "10:05", "end": "11:40", "course_name": "体育"},
    ], ensure_ascii=False), encoding="utf-8")

    items = course_module.load_weekly(str(path))
    monday = course_module.courses_on(items, 1)
    assert [c["course_name"] for c in monday] == ["高数", "英语"]
    assert course_module.courses_on(items, 3) == []
    assert course_module.load_weekly(str(tmp_path / "missing.json")) == []


def test_sync_day_writes_selected_weekday(tmp_path):
    """周课表同步：只写入指定星期的课，并清空原有课程。"""
    schedule = make_schedule(tmp_path)
    schedule.add_course(datetime.strptime("06:00", "%H:%M").time(), "旧课程")

    items = [
        {"weekday": 5, "start": "08:00", "end": "09:35", "course_name": "理工应用英语"},
        {"weekday": 5, "start": "10:05", "end": "11:40", "course_name": "软件工程"},
        {"weekday": 1, "start": "08:00", "end": "09:35", "course_name": "人工智能基础"},
    ]
    synced = course_module.sync_day(schedule, items, 5)

    assert len(synced) == 2
    assert list(schedule.schedule.keys()) == ["08:00", "10:05"]
    assert schedule.schedule["08:00"]["course_name"] == "理工应用英语"
