from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


class AgentError(Exception):
    """Raised when an agent cannot complete its task."""


@dataclass
class JobContext:
    """Shared state that flows through the agent pipeline."""

    url: str
    raw_html: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    description: Optional[str] = None
    trimmed_description: Optional[str] = None
    contact_emails: List[str] = field(default_factory=list)
    contact_channels: List[str] = field(default_factory=list)
    salary_mentions: List[str] = field(default_factory=list)
    meta: Dict[str, object] = field(default_factory=dict)
    flags: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "acquisition": [],
            "content": [],
            "verification": [],
            "financial": [],
            "intelligence": [],
        }
    )

    def add_flag(self, category: str, message: str) -> None:
        bucket = self.flags.setdefault(category, [])
        if message not in bucket:
            bucket.append(message)


class Agent:
    """Interface for all agents in the workflow."""

    name: str = "agent"

    def run(self, context: JobContext) -> JobContext:  # pragma: no cover - interface
        raise NotImplementedError("Agents must implement run()")
