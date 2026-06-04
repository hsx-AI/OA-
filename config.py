import os

# 和风天气 API 配置
# 在 https://console.qweather.com 的"项目管理"中查看你的配置

# API Host — 以你控制台显示的为准
API_HOST = "https://pc5ctup9mw.re.qweatherapi.com"

# API Key
API_KEY = "87cfafd40e8942fb898af54276b0bb49"

# 推送模式 — 内部服务器的地址（部署在局域网内其他机器上）
INTERNAL_SERVER_URL = os.getenv("INTERNAL_SERVER_URL", "http://10.42.60.230:8000/api/info-feed")

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

# 需要推送的新闻频道。中国新闻网 RSS 目前这些源是持续更新的。
NEWS_CHANNELS = [
    {"key": "scroll", "label": "即时", "rss_url": "https://www.chinanews.com.cn/rss/scroll-news.xml"},
    {"key": "import", "label": "要闻", "rss_url": "https://www.chinanews.com.cn/rss/importnews.xml"},
    {"key": "politics", "label": "时政", "rss_url": "https://www.chinanews.com.cn/rss/china.xml"},
    {"key": "world", "label": "国际", "rss_url": "https://www.chinanews.com.cn/rss/world.xml"},
    {"key": "finance", "label": "财经", "rss_url": "https://www.chinanews.com.cn/rss/finance.xml"},
    {"key": "society", "label": "社会", "rss_url": "https://www.chinanews.com.cn/rss/society.xml"},
    {"key": "life", "label": "生活", "rss_url": "https://www.chinanews.com.cn/rss/life.xml"},
    {"key": "health", "label": "健康", "rss_url": "https://www.chinanews.com.cn/rss/health.xml"},
    {"key": "ent", "label": "文娱", "rss_url": "https://www.chinanews.com.cn/rss/culture.xml"},
    {"key": "sports", "label": "体育", "rss_url": "https://www.chinanews.com.cn/rss/sports.xml"},
]

# 每个栏目最终推送到内网的新闻条数。
NEWS_TARGET_COUNT = 10

# 来源黑名单。按来源或标题关键词过滤，不需要过滤时保持空列表。
NEWS_SOURCE_BLOCKLIST = []

# 长期运行模式：每天早、中、晚三次推送。格式为 HH:MM，使用运行 pusher 电脑的本地时间。
PUSH_SCHEDULE_TIMES = ["07:30", "12:30", "18:30"]

# 服务启动时是否先立即推送一次；设置为 False 则等到下一个计划时间。
RUN_ON_START = True

# 每次推送新闻前清理主系统旧新闻详情和旧图片，避免缓存长期留存。
CLEAR_NEWS_CACHE_BEFORE_PUSH = True
