from __future__ import annotations

from .agents import AgentError, JobContext
from .pipeline.langgraph_pipeline import build_agent_graph


class ParentOrchestrator:
    """Orchestrates the scraping and analysis via LangGraph."""

    def __init__(self) -> None:
        self.graph = build_agent_graph(include_scrape=True)

    def process_job(self, url: str) -> dict:
        context = JobContext(url=url)

        try:
            result = self.graph.invoke({"context": context})
            context = result["context"]
        except AgentError as exc:
            return {"verdict": "error", "reason": str(exc)}

        return {
            "verdict": context.meta.get("verdict", "unknown"),
            "risk_score": context.meta.get("risk_score", 0),
            "confidence": context.meta.get("confidence", 0),
            "flags": context.flags,
            "summary": context.meta,
            "source": {
                "url": context.url,
                "title": context.title,
                "company": context.company,
            },
            "recommendation": self._generate_recommendation(context),
        }
    
    def _generate_recommendation(self, context: JobContext) -> str:
        """Generate user-friendly recommendation based on verdict."""
        verdict = context.meta.get("verdict", "unknown")
        is_trusted = context.meta.get("trusted_domain", False)
        scraping_incomplete = context.meta.get("scraping_incomplete", False)
        
        if verdict == "incomplete_data":
            return (
                "⚠️ Unable to analyze fully - site uses JavaScript rendering. "
                "Visit the URL directly in your browser to review the full job posting. "
                "Domain appears to be from a known employment platform."
            )
        elif verdict == "fake":
            return (
                "🚨 HIGH RISK - Multiple red flags detected. "
                "Proceed with extreme caution or avoid this posting."
            )
        elif verdict == "suspicious":
            return (
                "⚠️ CAUTION - Some concerning signals found. "
                "Research the company independently before applying."
            )
        elif is_trusted and scraping_incomplete:
            return (
                "ℹ️ Trusted domain but incomplete scraping. "
                "Visit the job page directly to review full details."
            )
        else:
            return (
                "✅ No major red flags detected. "
                "Still verify company legitimacy independently before sharing personal info."
            )
