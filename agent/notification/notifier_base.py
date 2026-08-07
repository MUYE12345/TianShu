"""推送器基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass
class NotifyContent:
    """推送内容"""
    title: str = ""
    summary: str = ""
    articles: List[dict] = field(default_factory=list)
    content_type: str = "news"
    weather: dict = field(default_factory=dict)  # 天气信息: {city, temp, text, suggestion}


class NotifierBase(ABC):
    """推送器基类"""

    @abstractmethod
    def send(self, content: NotifyContent) -> bool:
        pass

    @abstractmethod
    def validate_config(self) -> tuple:
        return False, "未配置"
