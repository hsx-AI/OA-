# 和风天气 API 配置
# 在 https://console.qweather.com 的"项目管理"中查看你的配置

# API Host — 以你控制台显示的为准
API_HOST = "https://pc5ctup9mw.re.qweatherapi.com"

# API Key
API_KEY = "87cfafd40e8942fb898af54276b0bb49"

# 聚合数据 API Key（新闻接口）
JUHE_NEWS_KEY = "0efb4cd4cdc496bb05aacf1c432ef881"

# 推送模式 — 内部服务器的地址（部署在局域网内其他机器上）
INTERNAL_SERVER_URL = "http://127.0.0.1:5000"

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
NEWS_TYPES = ["top", "guonei", "keji"]
