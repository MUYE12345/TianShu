from abc import ABC, abstractmethod
from typing import List, Optional


class BaseRule(ABC):
    @abstractmethod
    def check(self, user_id: int, context: dict = None) -> List[dict]:
        pass
