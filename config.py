import os

# 和风天气 API 配置
# 在 https://console.qweather.com 的"项目管理"中查看你的配置

# API Host — 以你控制台显示的为准
API_HOST = "https://pc5ctup9mw.re.qweatherapi.com"

# API Key
API_KEY = "87cfafd40e8942fb898af54276b0bb49"

# 聚合数据 API Key（新闻接口）
JUHE_NEWS_KEY = "0efb4cd4cdc496bb05aacf1c432ef881"

# 推送模式 — 内部服务器的地址（部署在局域网内其他机器上）
INTERNAL_SERVER_URL = os.getenv("INTERNAL_SERVER_URL", "http://127.0.0.1:8000/api/info-feed")

# 需要定时推送天气的城市 LocationID 列表
LOCATIONS = [
    "101010100",  # 北京
    "101020100",  # 上海
    "101280101",  # 广州
    "101280601",  # 深圳
    "101270101",  # 成都
    "101210101",  # 杭州
    "101050101",  # 哈尔滨
]

# 需要推送的新闻类型（留空默认推头条）
NEWS_TYPES = ["top", "guonei", "guoji", "caijing", "yule", "tiyu", "junshi", "keji", "shehui"]

# 每个栏目最终推送到内网的新闻条数。pusher 会翻多页，过滤掉不想展示的来源后凑够该数量。
NEWS_TARGET_COUNT = 10
NEWS_MAX_PAGES = 5

# 聚合“新闻头条”接口不支持地区参数，国内栏目偶尔会被地方站点刷屏。
# 这里先默认过滤鲁网；如需保留，改成空列表 []。
NEWS_SOURCE_BLOCKLIST = ["鲁网"]
