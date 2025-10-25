"""Service utilities for the job verifier package."""

from .llm import chat, llm_available, structured_chat

__all__ = ["chat", "structured_chat", "llm_available", "analyze_job", "scrape_job"]


def analyze_job(*args, **kwargs):
    from .analysis import analyze_job as _analyze_job

    return _analyze_job(*args, **kwargs)


def scrape_job(*args, **kwargs):
    from .scraper_agent import scrape_job as _scrape_job

    return _scrape_job(*args, **kwargs)
