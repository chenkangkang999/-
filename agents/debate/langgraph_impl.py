"""Bounded, evidence-grounded conflict detection, challenge and adjudication."""
from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.base.context import AgentContext
from agents.contracts import ConflictDetection, DebateChallenge, DebateVerdict
from agents.llm.support import complete_json, evidence, response_metadata, validate_citation_ids


class DebateState(TypedDict, total=False):
    context: AgentContext
    payload: dict[str, Any]
    detection: dict[str, Any]
    challenge: dict[str, Any]
    verdict: dict[str, Any]
    rounds: list[dict[str, Any]]
    llm_calls: list[dict[str, Any]]
    round: int
    max_rounds: int


def detect(state: DebateState) -> dict[str, Any]:
    output, response = complete_json(state["context"], "debate", "debate_detect",
                                     state["payload"], ConflictDetection)
    sources = {step["agent"]: step for step in state["payload"]["upstream"]
               if step.get("available") and step["agent"] != "retrieval"}
    citations = evidence(state["context"])
    for conflict in output.conflicts:
        if len({position.agent for position in conflict.positions}) < 2:
            raise ValueError("DEBATE_REQUIRES_DISTINCT_SOURCES")
        for position in conflict.positions:
            if position.agent not in sources:
                raise ValueError("UNKNOWN_DEBATE_SOURCE")
            source = sources[position.agent]
            quoted_source = source["content"] + json.dumps(source["metadata"], ensure_ascii=False)
            if position.claim not in quoted_source:
                raise ValueError("UNSUPPORTED_DEBATE_CLAIM")
            validate_citation_ids(position.citation_ids, citations)
    return {"detection": output.model_dump(), "llm_calls": [response_metadata(response)]}


def challenge(state: DebateState) -> dict[str, Any]:
    payload = {**state["payload"], "conflicts": state["detection"]["conflicts"],
               "previous_rounds": state.get("rounds", [])}
    output, response = complete_json(state["context"], "debate", "debate_challenge",
                                     payload, DebateChallenge)
    return {"challenge": output.model_dump(), "round": state.get("round", 0) + 1,
            "llm_calls": [*state["llm_calls"], response_metadata(response)]}


def adjudicate(state: DebateState) -> dict[str, Any]:
    payload = {**state["payload"], "conflicts": state["detection"]["conflicts"],
               "challenge": state["challenge"], "previous_rounds": state.get("rounds", [])}
    output, response = complete_json(state["context"], "debate", "debate_adjudicate",
                                     payload, DebateVerdict)
    validate_citation_ids(output.citation_ids, evidence(state["context"]))
    verdict = output.model_dump()
    return {"verdict": verdict,
            "rounds": [*state.get("rounds", []),
                       {"round": state["round"], "challenge": state["challenge"],
                        "verdict": verdict}],
            "llm_calls": [*state["llm_calls"], response_metadata(response)]}


def route_detection(state: DebateState) -> str:
    return "challenge" if state["detection"]["conflicts"] else "finish"


def route_verdict(state: DebateState) -> str:
    return ("challenge" if state["verdict"]["unresolved"]
            and state["round"] < state["max_rounds"] else "finish")


def build_graph():
    graph = StateGraph(DebateState)
    graph.add_node("detect", detect)
    graph.add_node("challenge", challenge)
    graph.add_node("adjudicate", adjudicate)
    graph.add_edge(START, "detect")
    graph.add_conditional_edges("detect", route_detection,
                                {"challenge": "challenge", "finish": END})
    graph.add_edge("challenge", "adjudicate")
    graph.add_conditional_edges("adjudicate", route_verdict,
                                {"challenge": "challenge", "finish": END})
    return graph.compile()
