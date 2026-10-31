"""多智能体框架（与 Django 解耦，可单独 import 测试）。"""
from agents.base.agent import AgentResult, BaseAgent
from agents.base.coordinator import Coordinator
from agents.base.registry import get_agent, list_agents, register

__all__ = ("AgentResult", "BaseAgent", "Coordinator", "get_agent", "list_agents", "register")
