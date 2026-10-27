"""RSS 解析、城市过滤、缓存降级与建议拼接测试。"""
from __future__ import annotations

import json
import os

import news

SAMPLE_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <title>示例源</title>
  <item>
    <title><![CDATA[大连地铁 5 号线今日延长运营]]></title>
    <link>https://example.com/1</link>
    <pubDate>Thu, 23 Oct 2026 08:30:00 +0800</pubDate>
  </item>
  <item>
    <title>全国高校计算机大赛报名启动</title>
    <link>https://example.com/2</link>
    <pubDate>Thu, 23 Oct 2026 09:10:00 +0800</pubDate>
  </item>
  <item>
    <title>大连地铁 5 号线今日延长运营</title>
    <link>https://example.com/1-dup</link>
    <pubDate>Thu, 23 Oct 2026 08:30:00 +0800</pubDate>
  </item>
</channel></rss>
"""


def test_parse_feed_reads_title_link_and_time():
    items = news.parse_feed(SAMPLE_RSS, "示例源")
    assert len(items) == 3
    assert items[0]["title"] == "大连地铁 5 号线今日延长运营"
    assert items[0]["link"] == "https://example.com/1"
    assert items[0]["published"].startswith("2026-10-23T08:30")
    assert items[0]["source"] == "示例源"


def test_parse_feed_tolerates_broken_xml():
    assert news.parse_feed("not xml at all", "坏源") == []


def test_filter_items_dedupes_and_puts_local_first():
    rows = news.filter_items(news.parse_feed(SAMPLE_RSS, "示例源"), "dalian")
    assert len(rows) == 2                      # 重复标题被去重
    assert rows[0]["local"] is True
    assert rows[0]["keyword"] == "大连"
    assert rows[1]["local"] is False


def test_filter_items_falls_back_to_default_city_keywords():
    rows = news.filter_items(news.parse_feed(SAMPLE_RSS, "示例源"), "unknown-city")
    assert rows[0]["local"] is True            # 未知城市退回大连关键词表
    assert any(row["local"] for row in rows)


def test_brief_prefers_local_and_limits_length():
    rows = news.filter_items(news.parse_feed(SAMPLE_RSS, "示例源"), "dalian")
    lines = news.brief(rows, count=1)
    assert lines == ["大连地铁5号线今日延长运营"]   # 空白被压掉，只取 1 条
    assert all(len(line) <= 35 for line in lines)


def test_append_to_advice_keeps_original_when_no_items():
    text = "当前体感温度26摄氏度，气温适宜。"
    assert news.append_to_advice(text, []) == text
    merged = news.append_to_advice(text, [{"title": "大连今日大风蓝色预警", "local": True}])
    assert merged.startswith(text)
    assert "本地资讯" in merged and "大风" in merged


def test_collect_uses_stale_cache_when_network_fails(tmp_path, monkeypatch):
    cache_path = tmp_path / "news_cache.json"
    cache_path.write_text(json.dumps({
        "city": "dalian",
        "updated": "2026-10-20T08:00",
        "items": [{"title": "缓存里的大连新闻", "link": "", "published": "", "local": True}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(news, "CACHE_PATH", str(cache_path))

    result = news.collect("dalian", 6)
    assert result["stale"] is True
    assert result["items"][0]["title"] == "缓存里的大连新闻"


def test_collect_switches_city_without_refetching(tmp_path, monkeypatch):
    """切换城市直接用缓存里的 raw 素材本地重排，不再重新抓 RSS。"""
    cache_path = tmp_path / "news_cache.json"
    monkeypatch.setattr(news, "CACHE_PATH", str(cache_path))
    monkeypatch.setattr(news, "fetch_feed", lambda *a, **k: news.parse_feed(SAMPLE_RSS, "示例源"))
    news.collect("dalian", 6)

    calls = {"n": 0}
    monkeypatch.setattr(news, "fetch_feed",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or [])
    switched = news.collect("beijing", 6)
    assert calls["n"] == 0                     # 没有为切城市重新请求外网
    assert switched["city"] == "beijing"
    assert switched["stale"] is False
    assert all(row["local"] is False for row in switched["items"])  # 大连新闻不算北京本地


def test_collect_writes_cache_after_successful_fetch(tmp_path, monkeypatch):
    cache_path = tmp_path / "news_cache.json"
    monkeypatch.setattr(news, "CACHE_PATH", str(cache_path))
    monkeypatch.setattr(news, "fetch_feed", lambda *a, **k: news.parse_feed(SAMPLE_RSS, "示例源"))

    result = news.collect("dalian", 6)
    assert result["stale"] is False
    assert os.path.exists(cache_path)
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["city"] == "dalian"
    assert payload["items"][0]["local"] is True
    assert payload["raw"]                       # 原始素材池一并落盘

    # 第二次调用命中缓存，不再打外网（fetch_feed 已被替换成计数器）
    calls = {"n": 0}
    monkeypatch.setattr(news, "fetch_feed", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or [])
    again = news.collect("dalian", 6)
    assert calls["n"] == 0
    assert again["stale"] is False
