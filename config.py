import os

# 和风天气 API 配置
# 在 https://console.qweather.com 的"项目管理"中查看你的配置

# API Host — 以你控制台显示的为准
API_HOST = "https://pc5ctup9mw.re.qweatherapi.com"

# API Key
API_KEY = "87cfafd40e8942fb898af54276b0bb49"

# 阿里云市场新闻 API 配置
ALIYUN_NEWS_URL = os.getenv("ALIYUN_NEWS_URL", "https://lznews.market.alicloudapi.com/lundroid/news")
ALIYUN_NEWS_APPCODE = os.getenv("ALIYUN_NEWS_APPCODE", "974d44fe8c3748d6be8ae902b55ed37b")
ALIYUN_NEWS_APPKEY = os.getenv("ALIYUN_NEWS_APPKEY", "205014539")
ALIYUN_NEWS_APPSECRET = os.getenv("ALIYUN_NEWS_APPSECRET", "Pv8qTFiUyg23QfiJUefZI6Wq3WbPBG2w")

# 推送模式 — 内部服务器的地址（部署在局域网内其他机器上）
INTERNAL_SERVER_URL = os.getenv("INTERNAL_SERVER_URL", "10.42.60.230:8000/api/info-feed")

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

# 需要推送的新闻频道。key 是主系统内部栏目名，channel 是阿里云 API 入参。
NEWS_CHANNELS = [
    {"key": "news", "label": "新闻", "channel": "新闻"},
    {"key": "junshi", "label": "军事", "channel": "军事"},
    {"key": "keji", "label": "科技", "channel": "科技"},
]

# 每个栏目最终推送到内网的新闻条数。
NEWS_TARGET_COUNT = 10
NEWS_MAX_PAGES = 5

# 来源黑名单。当前只推国际、军事、科技，先不额外过滤来源。
NEWS_SOURCE_BLOCKLIST = []

# 长期运行模式：每天早、中、晚三次推送。格式为 HH:MM，使用运行 pusher 电脑的本地时间。
PUSH_SCHEDULE_TIMES = ["07:30", "12:30", "18:30"]

# 服务启动时是否先立即推送一次；设置为 False 则等到下一个计划时间。
RUN_ON_START = True

# 每次推送新闻前清理主系统旧新闻详情和旧图片，避免缓存长期留存。
CLEAR_NEWS_CACHE_BEFORE_PUSH = True
