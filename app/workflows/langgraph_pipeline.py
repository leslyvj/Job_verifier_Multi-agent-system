from __future__ import annotations

from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents import (
    CompanyIntelligenceAgent,
    ContentAnalysisAgent,
    DataAcquisitionAgent,
    InformationExtractionAgent,
    JobContext,
    RiskSynthesisAgent,
    SourceVerificationAgent,
)


class AgentState(TypedDict):
    context: JobContext


def _add_common_nodes(graph: StateGraph, prev: str) -> None:
    graph.add_node("content_analysis", _content_node)
    graph.add_edge(prev, "content_analysis")

    graph.add_node("information_extraction", _information_node)
    graph.add_edge("content_analysis", "information_extraction")

    graph.add_node("company_intelligence", _company_node)
    graph.add_edge("information_extraction", "company_intelligence")

    graph.add_node("source_verification", _verification_node)
    graph.add_edge("company_intelligence", "source_verification")

    graph.add_node("risk_synthesis", _synthesis_node)
    graph.add_edge("source_verification", "risk_synthesis")
    graph.add_edge("risk_synthesis", END)


def _data_node(state: AgentState) -> AgentState:
    context = state["context"]
    agent = DataAcquisitionAgent()
    context = agent.run(context)
    return {"context": context}


def _content_node(state: AgentState) -> AgentState:
    context = state["context"]
    agent = ContentAnalysisAgent()
    context = agent.run(context)
    return {"context": context}


def _information_node(state: AgentState) -> AgentState:
    context = state["context"]
    agent = InformationExtractionAgent()
    context = agent.run(context)
    return {"context": context}


def _company_node(state: AgentState) -> AgentState:
    context = state["context"]
    agent = CompanyIntelligenceAgent()
    context = agent.run(context)
    return {"context": context}


def _verification_node(state: AgentState) -> AgentState:
    context = state["context"]
    agent = SourceVerificationAgent()
    context = agent.run(context)
    return {"context": context}


def _synthesis_node(state: AgentState) -> AgentState:
    context = state["context"]
    agent = RiskSynthesisAgent()
    context = agent.run(context)
    return {"context": context}


@lru_cache(maxsize=2)
def build_agent_graph(include_scrape: bool) -> Any:
    graph = StateGraph(AgentState)
    if include_scrape:
        graph.add_node("data_acquisition", _data_node)
        graph.add_edge(START, "data_acquisition")
        _add_common_nodes(graph, "data_acquisition")
    else:
        _add_common_nodes(graph, START)
    return graph.compile()
