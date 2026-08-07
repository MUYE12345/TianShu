"""爬虫黑名单"""
from urllib.parse import urlparse

BLACKLIST = [
    "zhihu.com", "www.zhihu.com",
    "xiaohongshu.com", "www.xiaohongshu.com",
    "weibo.com", "www.weibo.com",
    "weixin.qq.com", "mp.weixin.qq.com",
    "douyin.com", "tiktok.com",
    "bilibili.com", "www.bilibili.com",
    "csdn.net", "blog.csdn.net",
]

def is_blacklisted(url: str) -> bool:
    try:
        domain = urlparse(url).hostname or ""
        return any(domain == b or domain.endswith("." + b) for b in BLACKLIST)
    except Exception:
        return False
