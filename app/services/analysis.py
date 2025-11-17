"""Legacy analysis shim built on the agent pipeline."""

from __future__ import annotations

from app.agents import JobContext
from app.agents.data_acquisition import DataAcquisitionAgent
from app.workflows.langgraph_pipeline import build_agent_graph


def analyze_job(scraped_data: dict) -> dict:
    """Run the agent pipeline against pre-scraped data."""

    context = JobContext(url=scraped_data.get("url", ""))
    context.title = scraped_data.get("title")
    context.company = scraped_data.get("company")
    context.description = scraped_data.get("description")
    context.trimmed_description = DataAcquisitionAgent._trim_description(  # type: ignore[attr-defined]
        context.description
    )
    context.contact_emails = scraped_data.get("contact_emails", [])
    context.contact_channels = scraped_data.get("contact_channels", [])
    context.salary_mentions = scraped_data.get("salary_mentions", [])

    graph = build_agent_graph(include_scrape=False)
    result = graph.invoke({"context": context})
    context = result["context"]

    return {
        "verdict": context.meta.get("verdict", "unknown"),
        "confidence": context.meta.get("confidence", 0),
        "flags": context.flags,
        "summary": context.meta,
    }
