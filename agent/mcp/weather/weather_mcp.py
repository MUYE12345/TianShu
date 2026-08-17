"""
天气预报MCP — 华风爱科天气API

API 文档: 华风爱科天气.md
Base URL: https://openapi.weathercn.com

支持 "北京" 或 "北京.大兴区" 等城市/区县格式。
"""
import json
import re
import requests
from backend.config import settings

# 华风爱科 API Key 只从 settings.WEATHER_API_KEY(.env) 读取, 代码中不保留任何默认 Key(隐私不入库/不上传)
BASE_URL = "https://openapi.weathercn.com"

# 常见中国城市 → Location Key 映射（城市级别）
CITY_KEY_MAP: dict[str, str] = {
    "北京": "101924",
    "上海": "981931",
    "广州": "2332594",
    "深圳": "2332633",
    "杭州": "2333616",
    "成都": "2333429",
    "武汉": "979299",
    "南京": "2333033",
    "重庆": "1715563",
    "西安": "2333389",
    "天津": "102145",
    "苏州": "2332745",
    "长沙": "2332741",
    "郑州": "2344922",
    "东莞": "2333524",
    "青岛": "2345876",
    "沈阳": "2341258",
    "宁波": "2333903",
    "昆明": "2332743",
    "大连": "2346019",
    "厦门": "2332670",
    "合肥": "2333446",
    "佛山": "2332641",
    "福州": "2333054",
    "哈尔滨": "2341265",
    "济南": "2333545",
    "温州": "2333730",
    "长春": "2341290",
    "石家庄": "2344930",
    "常州": "2333106",
    "泉州": "2333804",
    "南宁": "2333799",
    "贵阳": "2332712",
    "南昌": "2333195",
    "太原": "2344948",
    "烟台": "2345901",
    "嘉兴": "2333333",
    "南通": "2333220",
    "金华": "2333659",
    "珠海": "2332629",
    "惠州": "2332604",
    "徐州": "2333559",
    "海口": "2332780",
    "乌鲁木齐": "2345082",
    "绍兴": "2333897",
    "中山": "2332686",
    "台州": "2333338",
    "兰州": "2344409",
}

# ---- 工具函数 ----


def _parse_location(text: str) -> tuple[str, str | None]:
    """解析输入文本，返回 (城市, 区县)

    "北京"         → ("北京", None)
    "北京.大兴区"  → ("北京", "大兴区")
    "北京大兴"     → ("北京", "大兴")
    "大兴区"       → ("大兴区", None)  —— 作为区名直接搜索
    """
    # 尝试 "城市.区县" 格式
    parts = text.split(".")
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0].strip(), parts[1].strip()

    # 尝试 "城市区县" 格式（如 北京大兴）
    m = re.match(r"^([一-鿿]{2,4}?)([一-鿿]{2,4}?(?:区|县|市))$", text)
    if m:
        return m.group(1), m.group(2)

    return text, None


def _search_city_key(city: str, api_key: str, district: str | None = None) -> str | None:
    """搜索城市/区县 → 返回 Location Key

    查询优先级：
      1. 指定区县 → GeoPosition → 区县级 Key（不取 ParentCity）
      2. 城市名 → 在线 text search（需权限）
      3. 城市名 → 内置映射表
      4. 城市名 → Nominatim geocoding → GeoPosition → Key
    """
    query_name = f"{city}{district}" if district else city

    # ---- 指定了区县：用 Nominatim + GeoPosition 直接查区县 Key ----
    if district:
        try:
            geo_resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": query_name,
                    "format": "json",
                    "limit": 1,
                    "accept-language": "zh",
                },
                headers={"User-Agent": "IntelligentHousekeeper/1.0"},
                timeout=10,
            ).json()
            if geo_resp and "lat" in geo_resp[0] and "lon" in geo_resp[0]:
                lat = geo_resp[0]["lat"]
                lon = geo_resp[0]["lon"]
                pos = requests.get(
                    f"{BASE_URL}/locations/v1/cities/geoposition/search.json",
                    params={"apikey": api_key, "q": f"{lat},{lon}", "language": "zh-cn"},
                    timeout=10,
                ).json()
                if pos.get("Key"):
                    return pos["Key"]
        except requests.RequestException:
            pass
        # 区县查不到时降级到城市级别
        return _search_city_key(city, api_key, district=None)

    # ---- 城市级别 ----
    # 1. 在线 text search
    try:
        resp = requests.get(
            f"{BASE_URL}/locations/v1/cities/search.json",
            params={"apikey": api_key, "q": city, "language": "zh-cn"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0].get("Key")
    except requests.RequestException:
        pass

    # 2. 内置城市映射
    if city in CITY_KEY_MAP:
        return CITY_KEY_MAP[city]

    # 3. Nominatim → GeoPosition → ParentCity.Key
    try:
        geo_resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city, "format": "json", "limit": 1, "accept-language": "zh"},
            headers={"User-Agent": "IntelligentHousekeeper/1.0"},
            timeout=10,
        ).json()
        if geo_resp and "lat" in geo_resp[0] and "lon" in geo_resp[0]:
            lat = geo_resp[0]["lat"]
            lon = geo_resp[0]["lon"]
            pos = requests.get(
                f"{BASE_URL}/locations/v1/cities/geoposition/search.json",
                params={"apikey": api_key, "q": f"{lat},{lon}", "language": "zh-cn"},
                timeout=10,
            ).json()
            key = pos.get("ParentCity", {}).get("Key") or pos.get("Key")
            if key:
                return key
    except requests.RequestException:
        pass

    return None


def _daily_forecast(loc_key: str, api_key: str, days: int = 5) -> dict:
    """逐日预报（1/5/10 天）"""
    day_map = {1: "1day", 5: "5day", 10: "10day"}
    return requests.get(
        f"{BASE_URL}/forecasts/v1/daily/{day_map.get(days, '5day')}/{loc_key}.json",
        params={"apikey": api_key, "language": "zh-cn", "details": "true"},
        timeout=10,
    ).json()


def _hourly_forecast(loc_key: str, api_key: str, hours: int = 1) -> list:
    """逐时预报（1/12/24 小时）"""
    hour_map = {1: "1hour", 12: "12hour", 24: "24hour"}
    resp = requests.get(
        f"{BASE_URL}/forecasts/v1/hourly/{hour_map.get(hours, '1hour')}/{loc_key}.json",
        params={"apikey": api_key, "language": "zh-cn"},
        timeout=10,
    ).json()
    return resp if isinstance(resp, list) else []


# ---- 入口函数 ----


def weather_handler(city: str) -> str:
    """获取天气和天气建议

    支持 "北京" / "北京.大兴区" / "北京大兴" 等格式。
    使用华风爱科天气 API，区县级可获得更精确的预报。
    """
    api_key = settings.WEATHER_API_KEY
    if not api_key:
        return json.dumps({"error": "未配置 WEATHER_API_KEY, 天气功能不可用。请在 .env 设置后重试。"}, ensure_ascii=False)

    try:
        # 1. 解析位置
        city_name, district = _parse_location(city)
        display_name = f"{city_name}{district}" if district else city_name

        # 2. 获取 Location Key
        loc_key = _search_city_key(city_name, api_key, district)
        if not loc_key:
            return json.dumps({"error": f"未找到位置: {display_name}"}, ensure_ascii=False)

        # 3. 当前天气（1 小时预报第一条）
        hourly = _hourly_forecast(loc_key, api_key, 1)
        current = {}
        if hourly:
            h = hourly[0]
            temp_val = h.get("Temperature", {}).get("Value", "")
            current = {
                "temp": f"{temp_val}°C",
                "text": h.get("IconPhrase", ""),
                "humidity": "",
                "wind": "",
            }
        else:
            # 用逐日第一条的 Day 段兜底
            fallback = _daily_forecast(loc_key, api_key, 1)
            daily_list = fallback.get("DailyForecasts", [])
            if daily_list:
                d = daily_list[0]
                temp = d.get("Temperature", {})
                day_data = d.get("Day", {})
                current = {
                    "temp": f'{temp.get("Maximum", {}).get("Value", "")}°C',
                    "text": day_data.get("IconPhrase", ""),
                    "humidity": "",
                    "wind": day_data.get("Wind", {}).get("Direction", {}).get("Localized", ""),
                }

        # 4. 5 日预报
        fc_data = _daily_forecast(loc_key, api_key, 5)
        daily_list = fc_data.get("DailyForecasts", [])
        headline = fc_data.get("Headline", {})

        forecast = []
        has_rain = False
        temps = []

        for d in daily_list:
            day_data = d.get("Day", {})
            temp = d.get("Temperature", {})
            t_min = temp.get("Minimum", {}).get("Value", "")
            t_max = temp.get("Maximum", {}).get("Value", "")

            air_q = next(
                (
                    a.get("Category", "")
                    for a in d.get("AirAndPollen", [])
                    if a.get("Name") == "AirQuality"
                ),
                "",
            )

            forecast.append({
                "date": d.get("Date", "")[:10],
                "temp": f"{t_min}-{t_max}°C",
                "weather": day_data.get("IconPhrase", ""),
                "wind": day_data.get("Wind", {}).get("Direction", {}).get("Localized", ""),
                "windSpeed": f'{day_data.get("Wind", {}).get("Speed", {}).get("Value", "")} km/h',
                "rainProb": day_data.get("PrecipitationProbability", 0),
                "airQuality": air_q,
            })

            if "雨" in day_data.get("IconPhrase", ""):
                has_rain = True
            try:
                temps.append(int(t_max))
            except (ValueError, TypeError):
                temps.append(20)

        # 5. 生活建议
        suggestion = {}
        if temps:
            avg_temp = sum(temps) / len(temps)
            suggestion = {
                "umbrella": "建议带伞" if has_rain else "无需带伞",
                "dressing": (
                    "炎热，穿短袖"
                    if avg_temp > 30
                    else "温暖，穿长袖T恤"
                    if avg_temp > 20
                    else "凉爽，穿外套"
                    if avg_temp > 10
                    else "寒冷，穿羽绒服"
                ),
            }

        return json.dumps(
            {
                "city": display_name,
                "current": current,
                "forecast": forecast,
                "headline": headline.get("Text", ""),
                "suggestion": suggestion,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return json.dumps({"error": f"天气查询失败: {e}"}, ensure_ascii=False)
