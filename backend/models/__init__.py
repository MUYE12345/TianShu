"""
ORM模型导入: 所有模型在此导入以便 Base.metadata 发现
"""
from backend.models.user import User
from backend.models.session import ChatSession, Message
from backend.models.news import DailyNews, CurrentNews, HotSummary
from backend.models.paper import Paper, PaperPage, PaperFigure
from backend.models.wiki import WikiPage, WikiVersion
from backend.models.plan import DailyPlan
from backend.models.memory import Memory
from backend.models.notification import PushLog
from backend.models.reminder import Reminder
from backend.models.setting import Setting
from backend.models.task import ScheduledTask
from backend.models.agent_group import AgentGroup
from backend.models.agent import Agent
from backend.models.agent_team import AgentTeam
from backend.models.model_provider import ModelProvider
from backend.models.kb import (KbNotebook, KbSource, KbMember, KbChat,
                               KbMessage, KbArtifact, KbChunk)

__all__ = [
    "User", "ChatSession", "Message",
    "DailyNews", "CurrentNews", "HotSummary",
    "Paper", "PaperPage", "PaperFigure",
    "WikiPage", "WikiVersion", "DailyPlan", "Memory",
    "PushLog", "Reminder", "Setting", "ScheduledTask", "AgentGroup",
    "Agent", "AgentTeam", "ModelProvider",
    "KbNotebook", "KbSource", "KbMember", "KbChat",
    "KbMessage", "KbArtifact", "KbChunk",
]
