"""Compatibility wrapper around the data acquisition agent."""

from ..agents import AgentError, DataAcquisitionAgent, JobContext


def scrape_job(url: str) -> dict:
    """Fetch job details and return a serializable snapshot."""

    context = JobContext(url=url)
    agent = DataAcquisitionAgent()

    try:
        context = agent.run(context)
    except AgentError as exc:
        return {"error": str(exc)}

    return {
        "url": context.url,
        "title": context.title,
        "company": context.company,
        "description": context.description,
        "contact_emails": context.contact_emails,
        "contact_channels": context.contact_channels,
        "salary_mentions": context.salary_mentions,
        "scraped_at": context.meta.get("scraped_at"),
    }
