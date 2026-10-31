"""Agent 注册表：装饰器自注册，按名字取用；重复注册直接报错。"""
from __future__ import annotations

from agents.base.agent import BaseAgent

_REGISTRY: dict[str, BaseAgent] = {}


def register(agent_cls: type[BaseAgent]):
    instance = agent_cls()
    if instance.name in _REGISTRY:
        raise ValueError(f"agent 重复注册: {instance.name}")
    _REGISTRY[instance.name] = instance
    return agent_cls


def get_agent(name: str) -> BaseAgent:
    return _REGISTRY[name]


def list_agents() -> list[dict[str, str]]:
    return [
        {"name": agent.name, "description": agent.description}
        for agent in sorted(_REGISTRY.values(), key=lambda a: a.name)
    ]


def load_all() -> None:
    """import specialists 包触发全部注册。"""
    import agents.specialists  # noqa: F401
