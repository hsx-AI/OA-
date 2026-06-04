"""
数据推送脚本 — 运行在**有公网权限的这台机器**上
定时从上游 API 抓取天气/新闻数据，下载图片，推送到内部服务器
"""
import requests
import re
import hashlib
import os
import sys
from config import API_HOST, API_KEY, JUHE_NEWS_KEY, INTERNAL_SERVER_URL, LOCATIONS, NEWS_TYPES


def push_data(data_type, key, data):
    """推送 JSON 数据到内部服务器"""
    try:
        resp = requests.post(
            f"{INTERNAL_SERVER_URL}/push/data",
            json={"type": data_type, "key": key, "data": data},
            timeout=10
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"  [ERR] 推送失败 {data_type}:{key} — {e}")
        return False


def upload_media(img_url):
    """下载外网图片并上传到内部服务器，返回内部访问地址"""
    try:
        # 下载图片
        img_data = requests.get(img_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}).content
        if len(img_data) < 100:
            return None

        # 生成文件名（基于 URL 哈希 + 原始扩展名）
        ext = img_url.rsplit(".", 1)[-1].split("?")[0] if "." in img_url else "jpg"
        if len(ext) > 5 or "/" in ext:
            ext = "jpg"
        name = hashlib.md5(img_url.encode()).hexdigest()[:16] + "." + ext

        # 上传到内部服务器
        files = {"file": (name, img_data, "image/" + ext)}
        resp = requests.post(f"{INTERNAL_SERVER_URL}/push/media", files=files, data={"name": name}, timeout=15)
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
        r = requests.get(f"{API_HOST}/v7/weather/now", params={"location": loc, "key": API_KEY}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            city = data.get("now", {}).get("text", loc)
            print(f"  实时: {data['now'].get('temp','?')}°C {data['now'].get('text','?')}")
            push_data("weather:now", loc, data)

        # 逐小时预报
        for hours in ["24h", "72h"]:
            r = requests.get(f"{API_HOST}/v7/weather/{hours}", params={"location": loc, "key": API_KEY}, timeout=15)
            if r.status_code == 200:
                push_data(f"weather:hourly:{hours}", loc, r.json())
                print(f"  逐小时({hours}): OK")

        # 每日预报
        for days in ["3d", "7d"]:
            r = requests.get(f"{API_HOST}/v7/weather/{days}", params={"location": loc, "key": API_KEY}, timeout=15)
            if r.status_code == 200:
                push_data(f"weather:daily:{days}", loc, r.json())
                print(f"  每日({days}): OK")


# ============================================================
# 新闻数据（含图片下载 + 上传）
# ============================================================

def fetch_and_push_news():
    print("\n===== 新闻数据 =====\n")

    # 先推送新闻列表
    for ntype in NEWS_TYPES:
        print(f"[新闻] 列表 type={ntype}")
        r = requests.get("https://v.juhe.cn/toutiao/index", params={
            "key": JUHE_NEWS_KEY, "type": ntype, "page_size": "10"
        }, timeout=15)
        if r.status_code != 200:
            continue
        data = r.json()

        items = data.get("result", {}).get("data", [])
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

            print(f"  详情: {item['title'][:30]}...")
            r2 = requests.get("https://v.juhe.cn/toutiao/content", params={
                "key": JUHE_NEWS_KEY, "uniquekey": uk
            }, timeout=15)
            if r2.status_code != 200:
                continue
            detail = r2.json()

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
