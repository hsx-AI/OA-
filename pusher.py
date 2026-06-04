"""
数据推送脚本 — 运行在**有公网权限的这台机器**上
定时从上游 API 抓取天气/新闻数据，下载图片，推送到内部服务器
"""
import argparse
import html as html_lib
import time
from datetime import datetime, timedelta
import requests
import re
import hashlib
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import (
    API_HOST,
    API_KEY,
    ALIYUN_NEWS_URL,
    ALIYUN_NEWS_APPCODE,
    INTERNAL_SERVER_URL,
    LOCATIONS,
    NEWS_CHANNELS,
    NEWS_TARGET_COUNT,
    NEWS_MAX_PAGES,
    NEWS_SOURCE_BLOCKLIST,
    PUSH_SCHEDULE_TIMES,
    RUN_ON_START,
    CLEAR_NEWS_CACHE_BEFORE_PUSH,
)


REQUEST_TIMEOUT = 30
ARTICLE_TIMEOUT = 60
MAX_ARTICLE_HTML_LENGTH = 200000
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})
SESSION.mount(
    "https://",
    HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.8, allowed_methods=["GET", "POST"])),
)
SESSION.mount(
    "http://",
    HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.8, allowed_methods=["GET", "POST"])),
)


def normalize_base_url(url):
    value = (url or "").strip().rstrip("/")
    if value and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        value = "http://" + value
    return value


INTERNAL_BASE_URL = normalize_base_url(INTERNAL_SERVER_URL)


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


def get_aliyun_news_json(params, label):
    """请求阿里云市场新闻 API。"""
    try:
        resp = SESSION.get(
            ALIYUN_NEWS_URL,
            params=params,
            headers={"Authorization": f"APPCODE {ALIYUN_NEWS_APPCODE}"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            print(f"  [WARN] {label} HTTP {resp.status_code} {resp.text[:160]}")
            return None
        return resp.json()
    except Exception as e:
        print(f"  [WARN] {label} 请求失败 — {e}")
        return None


def push_data(data_type, key, data):
    """推送 JSON 数据到内部服务器"""
    try:
        resp = SESSION.post(
            f"{INTERNAL_BASE_URL}/push/data",
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


def clear_remote_cache(scope="news", clear_media=True):
    try:
        resp = SESSION.post(
            f"{INTERNAL_BASE_URL}/push/clear",
            json={"scope": scope, "clear_media": clear_media},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(
                f"  清理缓存: scope={scope}, keys={data.get('removedKeys', 0)}, "
                f"media={data.get('removedMedia', 0)}"
            )
            return True
        print(f"  [WARN] 清理缓存失败 HTTP {resp.status_code} {resp.text[:160]}")
    except Exception as e:
        print(f"  [WARN] 清理缓存失败 — {e}")
    return False


def upload_media(img_url):
    """下载外网图片并上传到内部服务器，返回内部访问地址"""
    try:
        img_url = html_lib.unescape((img_url or "").strip())
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        if not img_url:
            return None
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
        resp = SESSION.post(f"{INTERNAL_BASE_URL}/push/media", files=files, data={"name": name}, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return f"{INTERNAL_BASE_URL}/uploads/{name}"
    except Exception as e:
        print(f"  [WARN] 图片上传失败: {img_url[:80]} — {e}")
    return None


def clean_article_html(html):
    """清理外部网页，避免脚本、样式和事件属性污染主系统页面。"""
    if not html:
        return ""
    html = re.sub(r"(?is)<!doctype.*?>", "", html)
    html = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", html)
    html = re.sub(r"(?is)<style\b[^>]*>.*?</style>", "", html)
    html = re.sub(r"(?is)<noscript\b[^>]*>.*?</noscript>", "", html)
    html = re.sub(r"(?is)<iframe\b[^>]*>.*?</iframe>", "", html)
    html = re.sub(r"(?is)<svg\b[^>]*>.*?</svg>", "", html)
    html = re.sub(r"(?is)<link\b[^>]*>", "", html)
    html = re.sub(r"(?is)<meta\b[^>]*>", "", html)
    html = re.sub(r"(?is)<input\b[^>]*>", "", html)
    html = re.sub(r"(?is)<button\b[^>]*>.*?</button>", "", html)
    html = re.sub(r"\s+on\w+\s*=\s*(['\"]).*?\1", "", html)
    html = re.sub(r"\s+style\s*=\s*(['\"]).*?\1", "", html)
    html = re.sub(r"\s+class\s*=\s*(['\"]).*?\1", "", html)
    html = re.sub(r"\s+id\s*=\s*(['\"]).*?\1", "", html)
    html = re.sub(r"(?is)<a\b([^>]*)>", r'<a\1 target="_blank" rel="noopener noreferrer">', html)
    return html.strip()


def find_article_fragment(html):
    """从网页里尽量截取正文区域；失败时返回 body。"""
    if not html:
        return ""
    candidates = [
        r"(?is)<article\b[^>]*>.*?</article>",
        r"(?is)<div\b[^>]*(?:id|class)=['\"][^'\"]*(?:article|content|main|post|text|detail)[^'\"]*['\"][^>]*>.*?</div>",
        r"(?is)<section\b[^>]*(?:id|class)=['\"][^'\"]*(?:article|content|main|post|text|detail)[^'\"]*['\"][^>]*>.*?</section>",
    ]
    best = ""
    for pattern in candidates:
        for match in re.finditer(pattern, html):
            fragment = match.group(0)
            text_len = len(re.sub(r"(?is)<[^>]+>", "", fragment).strip())
            if text_len > len(re.sub(r"(?is)<[^>]+>", "", best).strip()):
                best = fragment
    if best:
        return best
    body = re.search(r"(?is)<body\b[^>]*>(.*?)</body>", html)
    return body.group(1) if body else html


def rewrite_article_images(html, base_url):
    def replace_src(match):
        prefix = match.group(1)
        src = html_lib.unescape(match.group(2).strip())
        if src.startswith("data:"):
            return match.group(0)
        absolute = urljoin(base_url, src)
        internal_url = upload_media(absolute)
        return f'{prefix}"{internal_url or absolute}"'

    return re.sub(r'''(?i)(<img\b[^>]*\bsrc\s*=\s*)['"]([^'"]+)['"]''', replace_src, html)


def fetch_article_content(article_url, digest=""):
    if not article_url:
        return f"<p>{digest}</p>" if digest else ""
    candidate_urls = [article_url]
    if "m.163.com/" in article_url:
        candidate_urls.append(article_url.replace("https://m.163.com/", "https://www.163.com/"))
        candidate_urls.append(article_url.replace("http://m.163.com/", "https://www.163.com/"))
    try:
        for url in dict.fromkeys(candidate_urls):
            try:
                resp = SESSION.get(url, timeout=ARTICLE_TIMEOUT, headers={"Referer": "https://www.163.com/"})
            except Exception as e:
                print(f"  [WARN] 原文下载失败: {url[:100]} — {e}")
                continue
            if resp.status_code != 200:
                print(f"  [WARN] 原文下载失败 HTTP {resp.status_code}: {url[:100]}")
                continue
            resp.encoding = resp.apparent_encoding or resp.encoding
            html = resp.text[:MAX_ARTICLE_HTML_LENGTH]
            fragment = find_article_fragment(html)
            fragment = rewrite_article_images(fragment, url)
            fragment = clean_article_html(fragment)
            text = re.sub(r"(?is)<[^>]+>", "", fragment).strip()
            if len(text) >= max(60, len(digest)):
                return fragment
        return f"<p>{digest}</p>" if digest else ""
    except Exception as e:
        print(f"  [WARN] 原文下载失败: {article_url[:100]} — {e}")
        return f"<p>{digest}</p>" if digest else ""


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


def extract_news_items(data, channel):
    if not isinstance(data, dict):
        print(f"  [WARN] 新闻列表响应不是对象 channel={channel}: {data}")
        return []
    resp = data.get("resp")
    if isinstance(resp, dict) and str(resp.get("RespCode")) not in ("200", ""):
        print(f"  [WARN] 新闻列表接口返回异常 channel={channel}: {resp}")
        return []
    items = data.get("data")
    if not isinstance(items, list):
        print(f"  [WARN] 新闻列表 data 异常 channel={channel}: {items}")
        return []
    return items


def normalize_aliyun_news_item(item, category_key, category_label):
    docid = item.get("docid") or item.get("url") or item.get("title") or ""
    title = item.get("title") or ""
    digest = item.get("digest") or ""
    image_url = item.get("imgsrc") or ""
    return {
        "uniquekey": docid,
        "title": title,
        "date": item.get("ptime") or "",
        "category": category_label,
        "type": category_key,
        "author_name": item.get("source") or "",
        "url": item.get("url") or item.get("skipURL") or "",
        "thumbnail_pic_s": image_url,
        "digest": digest,
        "content": f"<p>{digest}</p>" if digest else "",
        "raw": item,
    }


def make_news_list_payload(items):
    return {
        "stat": "1",
        "result": {
            "data": items,
        },
    }


def fetch_news_page(channel, page):
    data = get_aliyun_news_json({
        "channel": channel,
        "page": str(page),
    }, f"新闻列表 {channel} 第{page}页")
    if not data:
        return None
    if not extract_news_items(data, channel):
        return None
    return data


def fetch_and_push_news():
    print("\n===== 新闻数据 =====\n")
    if CLEAR_NEWS_CACHE_BEFORE_PUSH:
        clear_remote_cache("news", clear_media=True)

    for channel_cfg in NEWS_CHANNELS:
        ntype = channel_cfg["key"]
        label = channel_cfg["label"]
        channel = channel_cfg["channel"]
        print(f"[新闻] 列表 channel={channel}")
        items = []
        seen_keys = set()
        for page in range(1, NEWS_MAX_PAGES + 1):
            page_data = fetch_news_page(channel, page)
            if not page_data:
                continue
            page_items = extract_news_items(page_data, channel)
            for raw_item in page_items:
                item = normalize_aliyun_news_item(raw_item, ntype, label)
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

        if not items:
            continue
        print(f"  获取到 {len(items)} 条新闻")

        # 列表缩略图也需要换成内网地址，否则无公网权限的客户端无法显示。
        for item in items:
            for thumb_field in ["thumbnail_pic_s"]:
                thumb = item.get(thumb_field, "")
                if thumb and thumb.startswith("http"):
                    internal_url = upload_media(thumb)
                    if internal_url:
                        item[thumb_field] = internal_url

        push_data("news:list", f"{ntype}:1", make_news_list_payload(items))
        for item in items:
            uk = item.get("uniquekey", "")
            if not uk:
                continue
            print(f"  详情: {item.get('title', '')[:30]}...")
            detail = dict(item)
            source_url = detail.get("url") or detail.get("raw", {}).get("skipURL") or ""
            article_content = fetch_article_content(source_url, detail.get("digest", ""))
            if article_content:
                detail["content"] = article_content
                detail["article_cached"] = True
            else:
                detail["article_cached"] = False
            push_data("news:detail", uk, detail)
            print(f"    推送完成")


# ============================================================
# Main
# ============================================================

def run_once():
    print(f"目标服务器: {INTERNAL_BASE_URL}")
    print(f"天气城市数: {len(LOCATIONS)}")
    print(f"新闻频道数: {len(NEWS_CHANNELS)}")

    fetch_and_push_weather()
    fetch_and_push_news()

    print(f"\n===== 完成 =====")


def parse_schedule_times(values):
    parsed = []
    for value in values:
        try:
            hour_text, minute_text = value.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            parsed.append((hour, minute, value))
        except Exception:
            print(f"[WARN] 忽略无效推送时间: {value}")
    return parsed


def next_run_time(now=None):
    now = now or datetime.now()
    schedule = parse_schedule_times(PUSH_SCHEDULE_TIMES)
    if not schedule:
        raise RuntimeError("PUSH_SCHEDULE_TIMES 为空或全部无效")
    candidates = []
    for hour, minute, _ in schedule:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        candidates.append(candidate)
    return min(candidates)


def run_service():
    print("===== 天气新闻 pusher 服务启动 =====")
    print(f"计划时间: {', '.join(PUSH_SCHEDULE_TIMES)}")
    if RUN_ON_START:
        try:
            run_once()
        except Exception as e:
            print(f"[ERR] 启动立即推送失败 — {e}")

    while True:
        target = next_run_time()
        wait_seconds = max(1, int((target - datetime.now()).total_seconds()))
        print(f"\n下次推送时间: {target.strftime('%Y-%m-%d %H:%M:%S')}，等待 {wait_seconds} 秒")
        time.sleep(wait_seconds)
        try:
            run_once()
        except Exception as e:
            print(f"[ERR] 计划推送失败 — {e}")


def main():
    parser = argparse.ArgumentParser(description="天气新闻内网推送服务")
    parser.add_argument("--once", action="store_true", help="只推送一次后退出")
    args = parser.parse_args()
    if args.once:
        run_once()
    else:
        run_service()


if __name__ == "__main__":
    main()
