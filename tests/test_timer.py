"""命令行录入校验测试：空输入、格式错误、过去时间、quit 退出。"""
from __future__ import annotations

from datetime import datetime

import timer
from course import Schedule


class FixedDateTime(datetime):
    """把 timer 里的“当前时间”固定为 2026-10-22 09:00，用例不再依赖真实时钟。"""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 22, 9, 0, 0)


def feed_inputs(monkeypatch, values):
    iterator = iter(values)
    monkeypatch.setattr("builtins.input", lambda *args: next(iterator))


def make_schedule(tmp_path) -> Schedule:
    return Schedule(str(tmp_path / "courses.json"))


def test_empty_name_is_rejected(tmp_path, monkeypatch, capsys):
    """B-6 第一条：空课程名必须被拦截。"""
    feed_inputs(monkeypatch, ["", "quit"])
    schedule = make_schedule(tmp_path)
    timer.init_course(schedule)
    assert "课程名不能为空" in capsys.readouterr().out
    assert len(schedule.schedule) == 0


def test_quit_exits_without_adding(tmp_path, monkeypatch):
    """B-6 第二条：输入 quit 立即退出。"""
    feed_inputs(monkeypatch, ["quit"])
    schedule = make_schedule(tmp_path)
    timer.init_course(schedule)
    assert len(schedule.schedule) == 0


def test_invalid_time_format_then_valid(tmp_path, monkeypatch, capsys):
    """B-6 第三条：25:99 触发 strptime 的 ValueError，重新输入合法时间后成功。"""
    monkeypatch.setattr(timer, "datetime", FixedDateTime)
    feed_inputs(monkeypatch, ["高等数学", "25:99", "09:30", "quit"])

    schedule = make_schedule(tmp_path)
    timer.init_course(schedule)
    assert "时间格式不正确" in capsys.readouterr().out
    assert schedule.schedule["09:30"]["course_name"] == "高等数学"


def test_past_time_is_rejected(tmp_path, monkeypatch, capsys):
    """边界：早于当前时间必须提示重输。"""
    monkeypatch.setattr(timer, "datetime", FixedDateTime)
    feed_inputs(monkeypatch, ["英语", "08:59", "09:30", "quit"])

    schedule = make_schedule(tmp_path)
    timer.init_course(schedule)
    assert "必须晚于当前时间" in capsys.readouterr().out
    assert "09:30" in schedule.schedule
