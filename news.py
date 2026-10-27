"""本地资讯模块：抓取公开 RSS，筛出与所在城市相关的新闻，拼进出口播报。

设计取舍：
  - 只用公开 RSS（中新网、人民网），不需要任何 API Key，断网时降级读缓存；
  - 缓存 30 分钟，避免每次刷新页面都打三次外网；
  - 只把 1~2 条标题级资讯拼进建议，不朗读正文，保证播报时长可控。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "data", "news_cache.json")

# 公开 RSS 源（已验证可访问）；name 用于界面标注来源
SOURCES = [
    {"name": "中国新闻网·滚动", "url": "https://www.chinanews.com.cn/rss/scroll-news.xml"},
    {"name": "中国新闻网·社会", "url": "https://www.chinanews.com.cn/rss/society.xml"},
    {"name": "人民网·时政", "url": "http://www.people.com.cn/rss/politics.xml"},
]

# 城市关键词：命中任一即视为本地相关；顺序即优先级
CITY_KEYWORDS = {
    "dalian": ["大连", "辽宁", "金普", "旅顺", "甘井子", "沙河口", "中山区", "高新园区", "庄河", "瓦房店"],
    "shuangliu": ["双流", "成都", "四川", "天府新区", "郫都", "温江"],
    "beijing": ["北京", "朝阳", "海淀", "通州", "雄安", "京津冀"],
    "shanghai": ["上海", "浦东", "徐汇", "虹桥", "长三角"],
    "guangzhou": ["广州", "广东", "天河", "番禺", "南沙", "粤港澳"],
    "shenzhen": ["深圳", "广东", "前海", "南山", "福田", "粤港澳"],
    "hangzhou": ["杭州", "浙江", "余杭", "西湖", "滨江"],
    "chengdu": ["成都", "四川", "天府新区", "高新", "郫都"],
    "wuhan": ["武汉", "湖北", "光谷", "汉口", "长江"],
    "xian": ["西安", "陕西", "雁塔", "长安", "关中"],
    "chongqing": ["重庆", "两江新区", "渝北", "成渝"],
    "nanjing": ["南京", "江苏", "江宁", "江北新区", "长三角"],
    "tianjin": ["天津", "滨海新区", "京津冀", "南开"],
    "qingdao": ["青岛", "山东", "市南", "崂山", "西海岸"],
    "shenyang": ["沈阳", "辽宁", "浑南", "铁西", "东北"],
}
DEFAULT_CITY = "dalian"

CACHE_TTL_MINUTES = 30
MAX_ITEMS = 12


def _decode(content: bytes) -> str:
    """RSS 可能是 UTF-8，也可能是 GB2312；按顺序尝试，避免乱码标题。"""
    for encoding in ("utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _node_text(node, tag: str) -> str:
    child = node.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _parse_time(raw: str) -> str:
    """把 RFC822 / 'YYYY-MM-DD HH:MM:SS' 统一成 ISO 字符串，失败就留空。"""
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).isoformat(timespec="minutes")
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).isoformat(timespec="minutes")
        except ValueError:
            continue
    return ""


def parse_feed(xml_text: str, source: str = "") -> list[dict]:
    """解析 RSS 文本，返回 [{title, link, published, source}]；坏 XML 返回空列表。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    items = []
    for node in root.iter("item"):
        title = _node_text(node, "title")
        if not title:
            continue
        items.append({
            "title": re.sub(r"\s+", " ", title),
            "link": _node_text(node, "link"),
            "published": _parse_time(_node_text(node, "pubDate")),
            "source": source,
        })
    return items


def fetch_feed(url: str, source: str = "", timeout: int = 10) -> list[dict]:
    """抓取单个 RSS；任何网络异常都返回空列表，由调用方决定降级。"""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        print(f"[资讯] 抓取失败 {url}: {exc}")
        return []
    return parse_feed(_decode(response.content), source)


def keywords_for(city_key: str | None) -> list[str]:
    return CITY_KEYWORDS.get(city_key or DEFAULT_CITY, CITY_KEYWORDS[DEFAULT_CITY])


def filter_items(items: list[dict], city_key: str | None) -> list[dict]:
    """本地新闻排前面，其余作为“综合资讯”补位；按标题去重。"""
    keywords = keywords_for(city_key)
    seen, local, general = set(), [], []
    for item in items:
        title = item.get("title", "")
        if not title or title in seen:
            continue
        seen.add(title)
        hit = next((k for k in keywords if k in title), None)
        row = dict(item)
        row["local"] = bool(hit)
        row["keyword"] = hit or ""
        (local if hit else general).append(row)
    local.sort(key=lambda r: r.get("published", ""), reverse=True)
    general.sort(key=lambda r: r.get("published", ""), reverse=True)
    return (local + general)[:MAX_ITEMS]


def _dedupe(items: list[dict], limit: int = 120) -> list[dict]:
    """按标题去重并截断，作为跨城市切换的原始素材池。"""
    seen, out = set(), []
    for item in items:
        title = item.get("title", "")
        if not title or title in seen:
            continue
        seen.add(title)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _read_cache() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _cache_fresh(cache: dict, ttl_minutes: int = CACHE_TTL_MINUTES) -> bool:
    stamp = cache.get("updated")
    if not stamp:
        return False
    try:
        updated = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    return datetime.now() - updated < timedelta(minutes=ttl_minutes)


def collect(city_key: str | None = None, limit: int = 6,
            force: bool = False, ttl_minutes: int = CACHE_TTL_MINUTES,
            cache_only: bool = False) -> dict:
    """返回 {'city','updated','stale','items'}；网络失败时回退到过期缓存。

    缓存里额外保存 raw 全量素材，切城市时直接在本地按关键词重排，
    不再重新抓三个 RSS，保证「换个城市马上看到当地资讯」。
    cache_only=True 时只读缓存、绝不访问外网，供“快速播报”使用：
    缓存缺失就返回空列表，宁可少一条资讯，也不让播报等三四个网络请求。
    """
    city_key = city_key or DEFAULT_CITY
    cache = _read_cache()
    raw = cache.get("raw") or []
    same_city = cache.get("city") == city_key
    fresh = _cache_fresh(cache, ttl_minutes)

    if cache_only:
        if same_city:
            items = cache.get("items", [])
        else:
            items = filter_items(raw, city_key) if raw else []
        return {
            "city": city_key,
            "updated": cache.get("updated", ""),
            "stale": not fresh,
            "items": items[:limit],
        }

    if raw and fresh and not force:
        items = cache.get("items", []) if same_city else filter_items(raw, city_key)
        return {
            "city": city_key,
            "updated": cache.get("updated", ""),
            "stale": False,
            "items": items[:limit],
        }

    batch = []
    for source in SOURCES:
        batch.extend(fetch_feed(source["url"], source["name"]))

    if not batch:
        # 全部源都失败：给过期缓存，标注 stale，界面显示“离线缓存”
        fallback = cache.get("items", []) if same_city else filter_items(raw, city_key)
        return {
            "city": city_key,
            "updated": cache.get("updated", ""),
            "stale": True,
            "items": fallback[:limit],
        }

    items = filter_items(batch, city_key)
    updated = datetime.now().isoformat(timespec="minutes")
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"city": city_key, "updated": updated, "items": items,
                   "raw": _dedupe(batch)}, f, ensure_ascii=False, indent=2)
    return {"city": city_key, "updated": updated, "stale": False,
            "items": items[:limit]}


def _shorten(title: str, width: int = 34) -> str:
    title = re.sub(r"\s+", "", title).strip("，。、 ")
    return title if len(title) <= width else title[:width] + "…"


def brief(items: list[dict], count: int = 2) -> list[str]:
    """把资讯压成 1~2 句可朗读短句，优先本地相关。"""
    picked = [row for row in items if row.get("local")][:count]
    if len(picked) < count:
        picked += [row for row in items if not row.get("local")][:count - len(picked)]
    return [_shorten(row["title"]) for row in picked]


def append_to_advice(advice: str, items: list[dict], count: int = 2) -> str:
    """在出行建议末尾追加本地资讯；没有可用资讯时原样返回。"""
    lines = brief(items, count)
    if not lines:
        return advice
    label = "一条" if len(lines) == 1 else "两条"
    return advice + f"顺便播报{label}本地资讯：" + "；".join(lines) + "。"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="本地实时资讯（RSS）")
    parser.add_argument("--city", default=DEFAULT_CITY, choices=sorted(CITY_KEYWORDS))
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--force", action="store_true", help="忽略缓存强制刷新")
    args = parser.parse_args(argv)

    result = collect(args.city, args.limit, force=args.force)
    print(f"城市：{result['city']} · 更新：{result['updated'] or '-'}"
          f"{' · 离线缓存' if result['stale'] else ''}")
    for index, row in enumerate(result["items"], 1):
        mark = "本地" if row.get("local") else "综合"
        print(f"{index}. [{mark}] {row['title']}  ({row.get('source') or '-'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
