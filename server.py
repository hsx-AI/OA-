"""
内部局域网服务器 — 接收 pusher 推送的数据并对外提供服务
部署在局域网内其他机器上，让所有内部设备都能访问
"""
from flask import Flask, request, jsonify, send_from_directory
import os
import json
from datetime import datetime

app = Flask(__name__)

# 内存存储
store = {}
MEDIA_DIR = "uploads"
os.makedirs(MEDIA_DIR, exist_ok=True)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============== 接收推送 ==============

@app.route("/push/data", methods=["POST"])
def push_data():
    """pusher 推送 JSON 数据到此接口"""
    body = request.get_json(force=True)
    data_type = body["type"]
    key = body["key"]
    store[f"{data_type}:{key}"] = body["data"]
    return jsonify({"status": "ok", "time": now()})


@app.route("/push/media", methods=["POST"])
def push_media():
    """pusher 推送媒体文件（图片/视频）到此接口"""
    name = request.form.get("name", "")
    file = request.files.get("file")
    if not file:
        return jsonify({"status": "error", "msg": "缺少文件"}), 400
    path = os.path.join(MEDIA_DIR, name)
    file.save(path)
    return jsonify({"status": "ok", "url": f"/uploads/{name}"})


# ============== 对外查询 ==============

@app.route("/api/weather/now")
def weather_now():
    location = request.args.get("location", "")
    data = store.get(f"weather:now:{location}")
    if data:
        return jsonify(data)
    return jsonify({"code": "error", "msg": f"未缓存该城市数据: {location}"}), 404


@app.route("/api/weather/hourly/<hours>")
def weather_hourly(hours):
    location = request.args.get("location", "")
    data = store.get(f"weather:hourly:{hours}:{location}")
    if data:
        return jsonify(data)
    return jsonify({"code": "error", "msg": "未缓存"}), 404


@app.route("/api/weather/daily/<days>")
def weather_daily(days):
    location = request.args.get("location", "")
    data = store.get(f"weather:daily:{days}:{location}")
    if data:
        return jsonify(data)
    return jsonify({"code": "error", "msg": "未缓存"}), 404


@app.route("/api/news/list")
def news_list():
    ntype = request.args.get("type", "top")
    page = request.args.get("page", "1")
    data = store.get(f"news:list:{ntype}:{page}")
    if data:
        return jsonify(data)
    return jsonify({"code": "error", "msg": "未缓存"}), 404


@app.route("/api/news/detail")
def news_detail():
    uniquekey = request.args.get("uniquekey", "")
    data = store.get(f"news:detail:{uniquekey}")
    if data:
        return jsonify(data)
    return jsonify({"code": "error", "msg": "未缓存"}), 404


@app.route("/uploads/<filename>")
def serve_media(filename):
    return send_from_directory(MEDIA_DIR, filename)


# ============== 状态页 ==============

@app.route("/")
def index():
    cached = list(store.keys())
    return f"""
    <h2>天气新闻中转 — 内部服务器</h2>
    <p>更新时间: {now()}</p>
    <p>已缓存 {len(store)} 条数据</p>
    <h3>已缓存 Key</h3>
    <pre>{json.dumps(cached, ensure_ascii=False, indent=2)}</pre>
    """


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
