"""
爬虫安全校验 — 防止 SSRF / 攻击其他平台

对任意 URL 抓取(web_crawler MCP / browser_crawler / 任何 fetch)统一做前置校验:
  1. 协议白名单: 仅 http/https
  2. 主机名解析 → 拒绝内网/回环/链路本地/多播/未指定/保留地址(SSRF 核心)
  3. 拒绝指向本地主机(localhost / 127.x / ::1 / 本机内网 IP)
  4. 可选域名白名单(allowed_hosts): 非白名单域名直接拒绝
  5. 拒绝 URL 中携带用户名/密码(凭据泄漏)

说明: DNS 重绑定(解析后目标改变)无法完全静态防御, 这里是尽力而为的第一道闸。
"""
import ipaddress
import socket
from urllib.parse import urlparse

# 允许的协议
ALLOWED_SCHEMES = ("http", "https")

# 拒绝的地址范围(SSRF 黑名单)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),        # 未指定/广播
    ipaddress.ip_network("10.0.0.0/8"),       # 内网
    ipaddress.ip_network("100.64.0.0/10"),    # 运营商级 NAT
    ipaddress.ip_network("127.0.0.0/8"),      # 回环
    ipaddress.ip_network("169.254.0.0/16"),   # 链路本地(含云元数据 169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),    # 内网
    ipaddress.ip_network("192.0.0.0/24"),     # IETF 协议分配
    ipaddress.ip_network("192.168.0.0/16"),   # 内网
    ipaddress.ip_network("198.18.0.0/15"),    # 基准测试
    ipaddress.ip_network("224.0.0.0/4"),      # 多播
    ipaddress.ip_network("240.0.0.0/4"),      # 保留
    ipaddress.ip_network("::1/128"),          # IPv6 回环
    ipaddress.ip_network("fc00::/7"),         # IPv6 唯一本地
    ipaddress.ip_network("fe80::/10"),        # IPv6 链路本地
    ipaddress.ip_network("ff00::/8"),         # IPv6 多播
]

# 永不爬取的主机名
_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata.google.internal"}


def _is_blocked_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # 无法解析的 IP 一律拒绝
    for net in _BLOCKED_NETWORKS:
        if addr in net:
            return True
    return False


def validate_url(url: str, allowed_hosts=None) -> str:
    """校验抓取 URL, 返回错误信息(空串 = 安全)"""
    if not url or not isinstance(url, str):
        return "URL 为空"
    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return f"URL 解析失败: {url}"

    # 1. 协议白名单
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        return f"仅允许 http/https 协议, 已拒绝: {scheme or '(无协议)'}"
    # 2. 凭据
    if parsed.username or parsed.password:
        return "URL 不允许携带用户名/密码"
    # 3. 主机名
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return "URL 缺少主机名"
    if host in _BLOCKED_HOSTNAMES:
        return f"禁止爬取本机地址: {host}"
    # 4. 域名白名单(可选)
    if allowed_hosts:
        ok = any(host == h.lower() or host.endswith("." + h.lower()) for h in allowed_hosts)
        if not ok:
            return f"域名不在白名单内, 已拒绝: {host}"
    # 5. IP 直连/IP 解析校验(SSRF)
    if host.replace(".", "").isdigit() or ":" in host:
        # 直接 IP
        if _is_blocked_ip(host):
            return f"目标为内网/保留地址, 已拒绝: {host}"
    else:
        try:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        except Exception:  # noqa: BLE001
            return f"域名解析失败: {host}"
        for info in infos:
            ip = info[4][0]
            if _is_blocked_ip(ip):
                return f"域名 {host} 解析到内网/保留地址({ip}), 已拒绝"
    return ""


def is_safe_url(url: str, allowed_hosts=None) -> bool:
    """便捷: 是否允许抓取"""
    return validate_url(url, allowed_hosts) == ""
