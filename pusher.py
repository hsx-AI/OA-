"""
数据推送脚本 — 运行在**有公网权限的这台机器**上
定时从上游 API 抓取天气/新闻数据，下载图片，推送到内部服务器
"""
import requests
import re
import hashlib
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import (
    API_HOST,
    API_KEY,
    JUHE_NEWS_KEY,
    INTERNAL_SERVER_URL,
    LOCATIONS,
    NEWS_TYPES,
    NEWS_TARGET_COUNT,
    NEWS_MAX_PAGES,
    NEWS_SOURCE_BLOCKLIST,
)


REQUEST_TIMEOUT = (5, 20)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})
SESSION.mount(
    "https://",
    HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.8, allowed_methods=["GET", "POST"])),
)
SESSION.mount(
    "http://",
    HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.8, allowed_methods=["GET", "POST"])),
)


def get_json(url, params, label):
    """请求上游 JSON；单次失败只影响当前条目，不中断整轮推送。"""
    try:
        resp = SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"  [WARN] {label} HTTP {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:
        print(f"  [WARN] {label} 请求失败 — {e}")
        return None


def push_data(data_type, key, data):
    """推送 JSON 数据到内部服务器"""
    try:
        resp = SESSION.post(
            f"{INTERNAL_SERVER_URL}/push/data",
            json={"type": data_type, "key": key, "data": data},
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            return True
        print(f"  [ERR] 推送失败 {data_type}:{key} — HTTP {resp.status_code} {resp.text[:120]}")
        return False
    except Exception as e:
        print(f"  [ERR] 推送失败 {data_type}:{key} — {e}")
        return False


def upload_media(img_url):
    """下载外网图片并上传到内部服务器，返回内部访问地址"""
    try:
        # 下载图片
        resp = SESSION.get(img_url, timeout=REQUEST_TIMEOUT, stream=True)
        if resp.status_code != 200:
            print(f"  [WARN] 图片下载失败 HTTP {resp.status_code}: {img_url[:80]}")
            return None
        img_data = resp.content
        if len(img_data) < 100:
            return None

        # 生成文件名（基于 URL 哈希 + 原始扩展名）
        ext = img_url.rsplit(".", 1)[-1].split("?")[0] if "." in img_url else "jpg"
        if len(ext) > 5 or "/" in ext:
            ext = "jpg"
        name = hashlib.md5(img_url.encode()).hexdigest()[:16] + "." + ext

        # 上传到内部服务器
        files = {"file": (name, img_data, "image/" + ext)}
        resp = SESSION.post(f"{INTERNAL_SERVER_URL}/push/media", files=files, data={"name": name}, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return f"{INTERNAL_SERVER_URL}/uploads/{name}"
    except Exception as e:
        print(f"  [WARN] 图片上传失败: {img_url[:80]} — {e}")
    return None


# ============================================================
# 天气数据
# ============================================================

def fetch_and_push_weather():
    print("\n===== 天气数据 =====\n")

    for loc in LOCATIONS:
        print(f"[天气] {loc}")

        # 实时天气
        data = get_json(f"{API_HOST}/v7/weather/now", {"location": loc, "key": API_KEY}, f"实时天气 {loc}")
        if data:
            if "now" not in data:
                print(f"  [WARN] 实时天气响应异常: {data}")
                continue
            print(f"  实时: {data['now'].get('temp','?')}°C {data['now'].get('text','?')}")
            push_data("weather:now", loc, data)

        # 逐小时预报
        for hours in ["24h", "72h"]:
            data = get_json(f"{API_HOST}/v7/weather/{hours}", {"location": loc, "key": API_KEY}, f"逐小时天气 {loc} {hours}")
            if data:
                push_data(f"weather:hourly:{hours}", loc, data)
                print(f"  逐小时({hours}): OK")

        # 每日预报
        for days in ["3d", "7d"]:
            data = get_json(f"{API_HOST}/v7/weather/{days}", {"location": loc, "key": API_KEY}, f"每日天气 {loc} {days}")
            if data:
                push_data(f"weather:daily:{days}", loc, data)
                print(f"  每日({days}): OK")


# ============================================================
# 新闻数据（含图片下载 + 上传）
# ============================================================

def is_blocked_news(item):
    source = item.get("author_name") or item.get("source") or ""
    title = item.get("title") or ""
    text = f"{source} {title}"
    return any(word and word in text for word in NEWS_SOURCE_BLOCKLIST)


def fetch_news_page(ntype, page):
    data = get_json("https://v.juhe.cn/toutiao/index", {
        "key": JUHE_NEWS_KEY,
        "type": ntype,
        "page": str(page),
        "page_size": str(NEWS_TARGET_COUNT),
        "is_filter": "0",
    }, f"新闻列表 {ntype} 第{page}页")
    if not data:
        return None
    items = data.get("result", {}).get("data", [])
    if not isinstance(items, list):
        print(f"  [WARN] 新闻列表响应异常 type={ntype}: {data}")
        return None
    return data


def fetch_and_push_news():
    print("\n===== 新闻数据 =====\n")

    # 先推送新闻列表
    for ntype in NEWS_TYPES:
        print(f"[新闻] 列表 type={ntype}")
        data = None
        items = []
        seen_keys = set()
        for page in range(1, NEWS_MAX_PAGES + 1):
            page_data = fetch_news_page(ntype, page)
            if not page_data:
                continue
            if data is None:
                data = page_data
            page_items = page_data.get("result", {}).get("data", [])
            for item in page_items:
                key = item.get("uniquekey") or item.get("title")
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                if is_blocked_news(item):
                    print(f"  [SKIP] 过滤来源: {(item.get('author_name') or '')} - {(item.get('title') or '')[:28]}")
                    continue
                items.append(item)
                if len(items) >= NEWS_TARGET_COUNT:
                    break
            if len(items) >= NEWS_TARGET_COUNT:
                break

        if not data:
            continue
        data.setdefault("result", {})["data"] = items
        print(f"  获取到 {len(items)} 条新闻")

        # 列表缩略图也需要换成内网地址，否则无公网权限的客户端无法显示。
        for item in items:
            for thumb_field in ["thumbnail_pic_s", "thumbnail_pic_s02", "thumbnail_pic_s03"]:
                thumb = item.get(thumb_field, "")
                if thumb and thumb.startswith("http"):
                    internal_url = upload_media(thumb)
                    if internal_url:
                        item[thumb_field] = internal_url

        push_data("news:list", f"{ntype}:1", data)

        # 逐条获取详情
        for item in items:
            uk = item.get("uniquekey", "")
            if not uk:
                continue

            print(f"  详情: {item.get('title', '')[:30]}...")
            detail = get_json("https://v.juhe.cn/toutiao/content", {
                "key": JUHE_NEWS_KEY,
                "uniquekey": uk,
            }, f"新闻详情 {uk}")
            if not detail:
                continue

            # 处理正文中的图片
            content = detail.get("result", {}).get("content", "")
            if content:
                # 找到所有 <img src="..."> 或 <img src='...'>
                img_urls = re.findall(r'''src=['"]([^'"]+)['"]''', content)
                for img_url in img_urls:
                    if not img_url.startswith("http"):
                        continue
                    internal_url = upload_media(img_url)
                    if internal_url:
                        content = content.replace(img_url, internal_url)
                detail["result"]["content"] = content

            # 处理缩略图
            for thumb_field in ["thumbnail_pic_s", "thumbnail_pic_s02", "thumbnail_pic_s03"]:
                thumb = detail.get("result", {}).get(thumb_field, "")
                if thumb and thumb.startswith("http"):
                    internal_url = upload_media(thumb)
                    if internal_url:
                        detail["result"][thumb_field] = internal_url

            push_data("news:detail", uk, detail.get("result", {}))
            print(f"    推送完成")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    print(f"目标服务器: {INTERNAL_SERVER_URL}")
    print(f"天气城市数: {len(LOCATIONS)}")
    print(f"新闻类型数: {len(NEWS_TYPES)}")

    fetch_and_push_weather()
    fetch_and_push_news()

    print(f"\n===== 完成 =====")
