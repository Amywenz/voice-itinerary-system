"""pytest 全局配置：把项目根加入 sys.path，避免从 tests/ 运行时找不到模块。"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")


@pytest.fixture(autouse=True)
def offline_news(monkeypatch):
    """测试不访问外网：RSS 抓取一律返回空列表，走缓存 / 降级分支。"""
    import news
    monkeypatch.setattr(news, "fetch_feed", lambda *args, **kwargs: [])
