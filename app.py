from flask import Flask, request, jsonify, Response
import requests
from urllib.parse import urlparse
import re

app = Flask(__name__)

# 从 config 中读取 API 配置
try:
    from config import API_HOST, API_KEY, JUHE_NEWS_KEY
except ImportError:
    API_HOST = "https://api.qweather.com"
    API_KEY = "YOUR_API_KEY_HERE"
    JUHE_NEWS_KEY = "YOUR_NEWS_KEY_HERE"


def proxy_to_qweather(path_suffix):
    """将请求转发到和风天气 API"""
    # 收集查询参数（LAN 用户传的参数原样转发）
    params = {}
    for key in request.args:
        params[key] = request.args.get(key)

    # 注入 API Key（和风天气私有个 Host 使用 key 参数认证）
    params["key"] = API_KEY

    # 构造目标 URL
    url = f"{API_HOST}{path_suffix}"

    try:
        resp = requests.get(url, params=params, timeout=15)
        # 返回原始 JSON 数据
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.Timeout:
        return jsonify({"code": "error", "msg": "上游 API 请求超时"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"code": "error", "msg": "无法连接上游 API"}), 502
    except Exception as e:
        return jsonify({"code": "error", "msg": str(e)}), 500


# ---- 三个天气接口 ----

@app.route("/weather/now")
def weather_now():
    """实时天气"""
    return proxy_to_qweather("/v7/weather/now")


@app.route("/weather/hourly/<hours>")
def weather_hourly(hours):
    """逐小时天气预报 → hours: 24h / 72h / 168h"""
    return proxy_to_qweather(f"/v7/weather/{hours}")


@app.route("/weather/daily/<days>")
def weather_daily(days):
    """每日天气预报 → days: 3d / 7d / 10d / 15d / 30d"""
    return proxy_to_qweather(f"/v7/weather/{days}")


def proxy_to_juhe(api_url):
    """将请求转发到聚合数据 API（新闻）"""
    params = {}
    for key in request.args:
        params[key] = request.args.get(key)
    params["key"] = JUHE_NEWS_KEY

    try:
        resp = requests.get(api_url, params=params, timeout=15)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.Timeout:
        return jsonify({"code": "error", "msg": "上游 API 请求超时"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"code": "error", "msg": "无法连接上游 API"}), 502
    except Exception as e:
        return jsonify({"code": "error", "msg": str(e)}), 500


# ---- 两个新闻接口 ----

@app.route("/news/list")
def news_list():
    """新闻列表"""
    return proxy_to_juhe("https://v.juhe.cn/toutiao/index")


@app.route("/news/detail")
def news_detail():
    """新闻详情"""
    return proxy_to_juhe("https://v.juhe.cn/toutiao/content")


@app.route("/news/detail/proxy")
def news_detail_proxy():
    """新闻详情（自动将正文中的图片URL替换为本地代理地址）"""
    params = {}
    for key in request.args:
        if key != "key":
            params[key] = request.args.get(key)
    params["key"] = JUHE_NEWS_KEY

    try:
        resp = requests.get("https://v.juhe.cn/toutiao/content", params=params, timeout=15)
        data = resp.json()
    except Exception as e:
        return jsonify({"code": "error", "msg": str(e)}), 500

    # 改写正文中的图片链接为本地代理地址
    if data.get("result", {}).get("content"):
        server_host = request.host
        content = data["result"]["content"]

        # 替换所有 <img src="..." 为本地代理地址
        def replace_img(match):
            src = match.group(1)
            proxy_url = f"http://{server_host}/proxy/media?url={src}"
            return f'<img src="{proxy_url}"'

        content = re.sub(r'''<img\s+[^>]*src=['"]([^'"]+)['"]''', replace_img, content)

        # 同时替换 thumbnail_pic_s 系列字段
        for key in ["thumbnail_pic_s", "thumbnail_pic_s02", "thumbnail_pic_s03"]:
            if data["result"].get(key):
                data["result"][key] = f"http://{server_host}/proxy/media?url={data['result'][key]}"
            if data["result"].get("detail", {}).get(key):
                data["result"]["detail"][key] = f"http://{server_host}/proxy/media?url={data['result']['detail'][key]}"

        data["result"]["content"] = content

    return jsonify(data), resp.status_code


@app.route("/proxy/media")
def proxy_media():
    """媒体文件代理 — 将外网图片/视频通过服务器中转"""
    url = request.args.get("url", "")
    if not url:
        return jsonify({"code": "error", "msg": "缺少 url 参数"}), 400

    try:
        # 只允许 http/https 地址
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return jsonify({"code": "error", "msg": "仅支持 http/https 链接"}), 400

        # 下载媒体文件
        resp = requests.get(url, timeout=20, stream=True,
                            headers={"User-Agent": "Mozilla/5.0"})

        content_type = resp.headers.get("Content-Type", "application/octet-stream")

        # 构建响应，透传二进制内容
        return Response(
            resp.iter_content(chunk_size=65536),
            status=resp.status_code,
            content_type=content_type,
            headers={
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*",
            }
        )
    except requests.exceptions.Timeout:
        return jsonify({"code": "error", "msg": "下载超时"}), 504
    except Exception as e:
        return jsonify({"code": "error", "msg": str(e)}), 500


# ---- 接口文档 ----

@app.route("/")
def index():
    return """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>天气中转服务 - 接口文档</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; color: #2c3e50; line-height: 1.7; }
  .container { max-width: 960px; margin: 0 auto; padding: 40px 20px; }
  h1 { font-size: 28px; margin-bottom: 8px; color: #1a1a2e; }
  .subtitle { color: #7f8c8d; margin-bottom: 32px; font-size: 14px; }
  h2 { font-size: 20px; margin: 36px 0 16px; padding-bottom: 8px; border-bottom: 2px solid #3498db; color: #1a1a2e; }
  h3 { font-size: 16px; margin: 20px 0 10px; color: #2c3e50; }
  .card { background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); padding: 24px; margin-bottom: 20px; }
  .endpoint { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .method { display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 13px; font-weight: 700; color: #fff; background: #27ae60; }
  .path { font-family: "SFMono-Regular", Consolas, monospace; font-size: 15px; font-weight: 600; word-break: break-all; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }
  th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #ecf0f1; }
  th { background: #f8f9fa; font-weight: 600; color: #555; font-size: 13px; }
  td { vertical-align: top; }
  .required { display: inline-block; background: #e74c3c; color: #fff; font-size: 11px; padding: 2px 6px; border-radius: 3px; margin-left: 4px; }
  .optional { display: inline-block; background: #95a5a6; color: #fff; font-size: 11px; padding: 2px 6px; border-radius: 3px; margin-left: 4px; }
  code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-family: "SFMono-Regular", Consolas, monospace; font-size: 13px; color: #e74c3c; }
  pre { background: #2d3436; color: #dfe6e9; padding: 16px 20px; border-radius: 6px; overflow-x: auto; font-size: 13px; line-height: 1.6; margin: 12px 0; }
  pre .k { color: #ff7675; }
  pre .s { color: #55efc4; }
  pre .c { color: #636e72; }
  .note { background: #fff3cd; border-left: 4px solid #f39c12; padding: 12px 16px; border-radius: 4px; margin: 16px 0; font-size: 14px; }
  a { color: #3498db; }
  @media (max-width: 640px) {
    .container { padding: 20px 12px; }
    table { font-size: 13px; }
    th, td { padding: 8px 10px; }
  }
</style>
</head>
<body>
<div class="container">

<h1>天气信息中转服务</h1>
<p class="subtitle">基于和风天气 API 的局域网天气数据中转站 &middot; v1.0</p>

<div class="note">
  本服务运行在局域网服务器上，通过服务器公网权限代理请求和风天气 API。局域网内设备无需连接公网即可获取天气数据。
</div>

<!-- ==================== 实时天气 ==================== -->
<h2>1. 实时天气</h2>
<div class="card">
  <div class="endpoint">
    <span class="method">GET</span>
    <span class="path">/weather/now</span>
  </div>
  <p>获取指定城市的实时天气数据，包括温度、体感温度、风力风向、相对湿度、大气压强、降水量、能见度、云量等。</p>

  <h3>查询参数</h3>
  <table>
    <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
    <tr>
      <td><code>location</code><span class="required">必填</span></td>
      <td>string</td>
      <td>是</td>
      <td>地区的 LocationID（如 <code>101010100</code>）或经纬度坐标（如 <code>116.41,39.92</code>）</td>
    </tr>
    <tr>
      <td><code>lang</code><span class="optional">可选</span></td>
      <td>string</td>
      <td>否</td>
      <td>多语言设置，默认中文。可选值见<a href="https://dev.qweather.com/docs/resource/language/" target="_blank">和风天气多语言文档</a></td>
    </tr>
    <tr>
      <td><code>unit</code><span class="optional">可选</span></td>
      <td>string</td>
      <td>否</td>
      <td>单位制：<code>m</code>（公制，默认）、<code>i</code>（英制）</td>
    </tr>
  </table>

  <h3>请求示例</h3>
  <pre><span class="c"># 通过 LocationID 查询</span>
curl "http://&lt;服务器IP&gt;:5000/weather/now?location=101010100"

<span class="c"># 通过经纬度查询</span>
curl "http://&lt;服务器IP&gt;:5000/weather/now?location=116.41,39.92"

<span class="c"># 指定语言和单位</span>
curl "http://&lt;服务器IP&gt;:5000/weather/now?location=101010100&lang=en&unit=i"</pre>

  <h3>响应示例</h3>
  <pre>{
  <span class="s">"code"</span>: <span class="s">"200"</span>,
  <span class="s">"updateTime"</span>: <span class="s">"2020-06-30T22:00+08:00"</span>,
  <span class="s">"now"</span>: {
    <span class="s">"obsTime"</span>:   <span class="s">"2020-06-30T21:40+08:00"</span>,
    <span class="s">"temp"</span>:      <span class="s">"24"</span>,
    <span class="s">"feelsLike"</span>: <span class="s">"26"</span>,
    <span class="s">"text"</span>:      <span class="s">"多云"</span>,
    <span class="s">"windDir"</span>:   <span class="s">"东南风"</span>,
    <span class="s">"windScale"</span>: <span class="s">"1"</span>,
    <span class="s">"windSpeed"</span>: <span class="s">"3"</span>,
    <span class="s">"humidity"</span>:  <span class="s">"72"</span>,
    <span class="s">"precip"</span>:    <span class="s">"0.0"</span>,
    <span class="s">"pressure"</span>:  <span class="s">"1003"</span>,
    <span class="s">"vis"</span>:       <span class="s">"16"</span>,
    <span class="s">"cloud"</span>:     <span class="s">"10"</span>,
    <span class="s">"dew"</span>:       <span class="s">"21"</span>
  }
}</pre>
</div>

<!-- ==================== 逐小时预报 ==================== -->
<h2>2. 逐小时天气预报</h2>
<div class="card">
  <div class="endpoint">
    <span class="method">GET</span>
    <span class="path">/weather/hourly/{hours}</span>
  </div>
  <p>获取全球城市未来 24-168 小时逐小时天气预报，包括温度、天气状况、风力、风速、风向、相对湿度、大气压强、降水概率、云量等。</p>

  <h3>路径参数</h3>
  <table>
    <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
    <tr>
      <td><code>hours</code><span class="required">必填</span></td>
      <td>string</td>
      <td>是</td>
      <td>预报小时数，可选值：<code>24h</code> / <code>72h</code> / <code>168h</code></td>
    </tr>
  </table>

  <h3>查询参数</h3>
  <table>
    <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
    <tr>
      <td><code>location</code><span class="required">必填</span></td>
      <td>string</td>
      <td>是</td>
      <td>LocationID 或 "经度,纬度"</td>
    </tr>
    <tr>
      <td><code>lang</code><span class="optional">可选</span></td>
      <td>string</td>
      <td>否</td>
      <td>多语言设置</td>
    </tr>
    <tr>
      <td><code>unit</code><span class="optional">可选</span></td>
      <td>string</td>
      <td>否</td>
      <td><code>m</code>（公制）或 <code>i</code>（英制）</td>
    </tr>
  </table>

  <h3>请求示例</h3>
  <pre><span class="c"># 查询未来 24 小时预报</span>
curl "http://&lt;服务器IP&gt;:5000/weather/hourly/24h?location=101010100"

<span class="c"># 查询未来 72 小时预报</span>
curl "http://&lt;服务器IP&gt;:5000/weather/hourly/72h?location=101010100"

<span class="c"># 查询未来 168 小时（7天）预报</span>
curl "http://&lt;服务器IP&gt;:5000/weather/hourly/168h?location=101010100"</pre>

  <h3>响应示例</h3>
  <pre>{
  <span class="s">"code"</span>: <span class="s">"200"</span>,
  <span class="s">"updateTime"</span>: <span class="s">"2021-02-16T13:35+08:00"</span>,
  <span class="s">"hourly"</span>: [
    {
      <span class="s">"fxTime"</span>:    <span class="s">"2021-02-16T15:00+08:00"</span>,
      <span class="s">"temp"</span>:      <span class="s">"2"</span>,
      <span class="s">"text"</span>:      <span class="s">"晴"</span>,
      <span class="s">"windDir"</span>:   <span class="s">"西北风"</span>,
      <span class="s">"windScale"</span>: <span class="s">"3-4"</span>,
      <span class="s">"windSpeed"</span>: <span class="s">"20"</span>,
      <span class="s">"humidity"</span>:  <span class="s">"11"</span>,
      <span class="s">"pop"</span>:       <span class="s">"0"</span>,
      <span class="s">"precip"</span>:    <span class="s">"0.0"</span>,
      <span class="s">"pressure"</span>:  <span class="s">"1025"</span>,
      <span class="s">"cloud"</span>:     <span class="s">"0"</span>,
      <span class="s">"dew"</span>:       <span class="s">"-25"</span>
    },
    { ... }
  ]
}</pre>
</div>

<!-- ==================== 每日预报 ==================== -->
<h2>3. 每日天气预报</h2>
<div class="card">
  <div class="endpoint">
    <span class="method">GET</span>
    <span class="path">/weather/daily/{days}</span>
  </div>
  <p>获取全球城市未来 3-30 天天气预报，包括日出日落、最高最低温度、天气状况（白天/夜间）、风力风向、相对湿度、大气压强、降水量、紫外线强度、能见度等。</p>

  <h3>路径参数</h3>
  <table>
    <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
    <tr>
      <td><code>days</code><span class="required">必填</span></td>
      <td>string</td>
      <td>是</td>
      <td>预报天数，可选值：<code>3d</code> / <code>7d</code> / <code>10d</code> / <code>15d</code> / <code>30d</code></td>
    </tr>
  </table>

  <h3>查询参数</h3>
  <table>
    <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
    <tr>
      <td><code>location</code><span class="required">必填</span></td>
      <td>string</td>
      <td>是</td>
      <td>LocationID 或 "经度,纬度"</td>
    </tr>
    <tr>
      <td><code>lang</code><span class="optional">可选</span></td>
      <td>string</td>
      <td>否</td>
      <td>多语言设置</td>
    </tr>
    <tr>
      <td><code>unit</code><span class="optional">可选</span></td>
      <td>string</td>
      <td>否</td>
      <td><code>m</code>（公制）或 <code>i</code>（英制）</td>
    </tr>
  </table>

  <h3>请求示例</h3>
  <pre><span class="c"># 查询未来 3 天预报</span>
curl "http://&lt;服务器IP&gt;:5000/weather/daily/3d?location=101010100"

<span class="c"># 查询未来 15 天预报</span>
curl "http://&lt;服务器IP&gt;:5000/weather/daily/15d?location=101010100"</pre>

  <h3>响应示例</h3>
  <pre>{
  <span class="s">"code"</span>: <span class="s">"200"</span>,
  <span class="s">"updateTime"</span>: <span class="s">"2021-11-15T16:35+08:00"</span>,
  <span class="s">"daily"</span>: [
    {
      <span class="s">"fxDate"</span>:    <span class="s">"2021-11-15"</span>,
      <span class="s">"sunrise"</span>:   <span class="s">"06:58"</span>,
      <span class="s">"sunset"</span>:    <span class="s">"16:59"</span>,
      <span class="s">"tempMax"</span>:   <span class="s">"12"</span>,
      <span class="s">"tempMin"</span>:   <span class="s">"-1"</span>,
      <span class="s">"textDay"</span>:   <span class="s">"多云"</span>,
      <span class="s">"textNight"</span>: <span class="s">"晴"</span>,
      <span class="s">"windDirDay"</span>: <span class="s">"东北风"</span>,
      <span class="s">"windScaleDay"</span>: <span class="s">"1-2"</span>,
      <span class="s">"humidity"</span>:  <span class="s">"65"</span>,
      <span class="s">"precip"</span>:    <span class="s">"0.0"</span>,
      <span class="s">"uvIndex"</span>:   <span class="s">"3"</span>
    },
    { ... }
  ]
}</pre>
</div>

<!-- ==================== 新闻列表 ==================== -->
<h2>4. 新闻列表</h2>
<div class="card">
  <div class="endpoint">
    <span class="method">GET</span>
    <span class="path">/news/list</span>
  </div>
  <p>获取聚合数据头条新闻列表，支持按类型筛选和分页。</p>

  <h3>查询参数</h3>
  <table>
    <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
    <tr>
      <td><code>type</code><span class="optional">可选</span></td>
      <td>string</td>
      <td>否</td>
      <td>新闻类型，如 <code>top</code>（头条，默认）、<code>guonei</code>（国内）、<code>guoji</code>（国际）、<code>yule</code>（娱乐）、<code>tiyu</code>（体育）、<code>keji</code>（科技）等</td>
    </tr>
    <tr>
      <td><code>page</code><span class="optional">可选</span></td>
      <td>string</td>
      <td>否</td>
      <td>页码，默认 <code>1</code></td>
    </tr>
    <tr>
      <td><code>page_size</code><span class="optional">可选</span></td>
      <td>string</td>
      <td>否</td>
      <td>每页条数，默认 <code>15</code></td>
    </tr>
    <tr>
      <td><code>is_filter</code><span class="optional">可选</span></td>
      <td>string</td>
      <td>否</td>
      <td>是否过滤内容，<code>1</code> 过滤（不返回详情内容）、<code>0</code> 不过滤</td>
    </tr>
  </table>

  <h3>请求示例</h3>
  <pre><span class="c"># 获取头条新闻</span>
curl "http://&lt;服务器IP&gt;:5000/news/list"

<span class="c"># 获取科技类新闻第2页</span>
curl "http://&lt;服务器IP&gt;:5000/news/list?type=keji&page=2"

<span class="c"># 获取国内新闻，过滤详情内容</span>
curl "http://&lt;服务器IP&gt;:5000/news/list?type=guonei&is_filter=1"</pre>

  <h3>响应字段说明</h3>
  <table>
    <tr><th>字段</th><th>说明</th></tr>
    <tr><td><code>stat</code></td><td>状态码，<code>1</code> 成功，<code>0</code> 失败</td></tr>
    <tr><td><code>data</code></td><td>新闻数据列表</td></tr>
    <tr><td><code>data[].uniquekey</code></td><td>新闻唯一标识（用于查询详情）</td></tr>
    <tr><td><code>data[].title</code></td><td>新闻标题</td></tr>
    <tr><td><code>data[].date</code></td><td>发布时间</td></tr>
    <tr><td><code>data[].category</code></td><td>新闻分类</td></tr>
    <tr><td><code>data[].author_name</code></td><td>作者/来源</td></tr>
    <tr><td><code>data[].url</code></td><td>新闻原文链接</td></tr>
    <tr><td><code>data[].thumbnail_pic_s</code></td><td>缩略图地址</td></tr>
  </table>
</div>

<!-- ==================== 新闻详情 ==================== -->
<h2>5. 新闻详情</h2>
<div class="card">
  <div class="endpoint">
    <span class="method">GET</span>
    <span class="path">/news/detail</span>
  </div>
  <p>根据新闻唯一标识获取新闻完整内容。</p>

  <h3>查询参数</h3>
  <table>
    <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
    <tr>
      <td><code>uniquekey</code><span class="required">必填</span></td>
      <td>string</td>
      <td>是</td>
      <td>新闻唯一标识，从新闻列表接口的 <code>uniquekey</code> 字段获取</td>
    </tr>
  </table>

  <h3>请求示例</h3>
  <pre><span class="c"># 获取新闻详情</span>
curl "http://&lt;服务器IP&gt;:5000/news/detail?uniquekey=xxx"

<span class="c"># 先查列表拿到 uniquekey，再查详情</span>
curl "http://&lt;服务器IP&gt;:5000/news/list?type=top&page_size=1"</pre>

  <h3>响应字段说明</h3>
  <table>
    <tr><th>字段</th><th>说明</th></tr>
    <tr><td><code>stat</code></td><td>状态码，<code>1</code> 成功，<code>0</code> 失败</td></tr>
    <tr><td><code>result.content</code></td><td>新闻正文内容（HTML 格式）</td></tr>
    <tr><td><code>result.title</code></td><td>新闻标题</td></tr>
    <tr><td><code>result.date</code></td><td>发布时间</td></tr>
    <tr><td><code>result.author_name</code></td><td>作者/来源</td></tr>
    <tr><td><code>result.url</code></td><td>新闻原文链接</td></tr>
    <tr><td><code>result.thumbnail_pic_s</code></td><td>缩略图地址</td></tr>
  </table>
</div>

<!-- ==================== 新闻详情（图片代理） ==================== -->
<h2>6. 新闻详情（媒体代理）</h2>
<div class="card">
  <div class="endpoint">
    <span class="method">GET</span>
    <span class="path">/news/detail/proxy</span>
  </div>
  <p>与 <code>/news/detail</code> 功能相同，但会<strong>自动将正文中的图片链接替换为本地代理地址</strong>。适合局域网内查看带图片的新闻内容。</p>

  <h3>查询参数</h3>
  <table>
    <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
    <tr>
      <td><code>uniquekey</code><span class="required">必填</span></td>
      <td>string</td>
      <td>是</td>
      <td>新闻唯一标识</td>
    </tr>
  </table>

  <h3>请求示例</h3>
  <pre><span class="c"># 获取新闻详情（自动代理图片）</span>
curl "http://&lt;服务器IP&gt;:5000/news/detail/proxy?uniquekey=xxx"

<span class="c"># 返回的 content 中所有 &lt;img src="..."&gt; 会变成：</span>
<span class="c"># &lt;img src="http://&lt;服务器IP&gt;:5000/proxy/media?url=原始图片地址"&gt;</span>
<span class="c"># 局域网设备可直接加载这些图片</span></pre>
</div>

<!-- ==================== 媒体代理 ==================== -->
<h2>7. 媒体文件代理</h2>
<div class="card">
  <div class="endpoint">
    <span class="method">GET</span>
    <span class="path">/proxy/media</span>
  </div>
  <p>将任意 HTTP(S) 图片、视频等媒体文件通过服务器中转，供局域网设备访问。</p>

  <h3>查询参数</h3>
  <table>
    <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
    <tr>
      <td><code>url</code><span class="required">必填</span></td>
      <td>string</td>
      <td>是</td>
      <td>需要代理的原始媒体文件 URL（需经过 URL 编码）</td>
    </tr>
  </table>

  <h3>请求示例</h3>
  <pre><span class="c"># 代理显示任意外网图片</span>
curl "http://&lt;服务器IP&gt;:5000/proxy/media?url=https://example.com/image.jpg"

<span class="c"># 在 HTML 中直接使用</span>
<span class="c"># &lt;img src="http://&lt;服务器IP&gt;:5000/proxy/media?url=https://..."&gt;</span></pre>
  <div class="note">
    支持所有 MIME 类型（图片、视频、音频等），会自动透传 Content-Type 并设置缓存。URL 参数无需手动编码，浏览器会自动处理。
  </div>
</div>

<!-- ==================== 通用说明 ==================== -->
<h2>通用说明</h2>
<div class="card">

  <h3>LocationID 说明</h3>
  <p>LocationID 是和风天气定义的地区标识。常见城市示例：</p>
  <table>
    <tr><th>城市</th><th>LocationID</th></tr>
    <tr><td>北京</td><td><code>101010100</code></td></tr>
    <tr><td>上海</td><td><code>101020100</code></td></tr>
    <tr><td>广州</td><td><code>101280101</code></td></tr>
    <tr><td>深圳</td><td><code>101280601</code></td></tr>
    <tr><td>成都</td><td><code>101270101</code></td></tr>
    <tr><td>杭州</td><td><code>101210101</code></td></tr>
  </table>
  <p style="margin-top:8px;font-size:14px;">完整城市代码请查阅 <a href="https://github.com/qwd/LocationList" target="_blank">和风天气 LocationList</a>，也可直接使用经纬度格式 <code>116.41,39.92</code> 查询。</p>

  <h3>响应状态码</h3>
  <table>
    <tr><th>HTTP 状态码</th><th>说明</th></tr>
    <tr><td>200</td><td>成功，JSON 中 <code>code</code> 字段为 <code>"200"</code></td></tr>
    <tr><td>404</td><td>请求的数据不存在（如错误的 LocationID）</td></tr>
    <tr><td>502</td><td>上游和风天气 API 连接失败</td></tr>
    <tr><td>504</td><td>上游和风天气 API 请求超时</td></tr>
  </table>

  <h3>错误码</h3>
  <p>当和风天气 API 返回错误时，原始错误码会透传。常见错误码：</p>
  <table>
    <tr><th>code</th><th>说明</th></tr>
    <tr><td><code>"200"</code></td><td>请求成功</td></tr>
    <tr><td><code>"204"</code></td><td>请求成功但无数据</td></tr>
    <tr><td><code>"400"</code></td><td>请求参数错误</td></tr>
    <tr><td><code>"401"</code></td><td>API Key 无效（检查 config.py 中的密钥）</td></tr>
    <tr><td><code>"403"</code></td><td>无权访问（订阅或权限不足）</td></tr>
    <tr><td><code>"404"</code></td><td>数据不存在</td></tr>
    <tr><td><code>"429"</code></td><td>请求超出配额</td></tr>
  </table>
  <p style="margin-top:8px;font-size:14px;">完整错误码请参考 <a href="https://dev.qweather.com/docs/resource/error-code/" target="_blank">和风天气错误码文档</a>。</p>
</div>

</div>
</body>
</html>"""


if __name__ == "__main__":
    # host="0.0.0.0" 让局域网内其他设备可以访问
    app.run(host="0.0.0.0", port=5000, debug=True)
