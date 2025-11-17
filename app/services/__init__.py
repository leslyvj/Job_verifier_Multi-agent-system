"""Service utilities with lightweight re-export helpers."""

from .llm import chat, llm_available, structured_chat


def analyze_job(*args, **kwargs):
    """Lazy import to avoid circular dependency during module load."""

    from .analysis import analyze_job as _analyze_job

    return _analyze_job(*args, **kwargs)


def scrape_job(*args, **kwargs):
    from .scraper_agent import scrape_job as _scrape_job

    return _scrape_job(*args, **kwargs)


__all__ = [
    "analyze_job",
    "chat",
    "llm_available",
    "scrape_job",
    "structured_chat",
]
