from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.services.llm import llm_available, structured_chat
from app.utils.logger import get_logger

from .base import Agent, JobContext

logger = get_logger(__name__)


class InformationExtractionAgent(Agent):
    """Build a structured summary of the job posting using LLM assistance."""

    name = "information_extraction"

    _PROMPT_TEMPLATE = (
        "You extract structured information from job postings. "
        "Return compact JSON with the following top-level keys: url, job_title, company, team, location, "
        "experience_required, education_required, skills (array), job_type, verified_domain, authenticity_score (0-1). "
        "Use the provided context. If a field is unknown, set it to null (or empty list for skills)."
    )

    def run(self, context: JobContext) -> JobContext:
        llm_payload = self._query_llm(context) if llm_available() else None
        profile = self._build_profile(context, llm_payload)

        context.meta["structured_profile"] = profile
        context.meta.setdefault("insights", {}).setdefault("information_extraction", {})[
            "raw_llm_output"
        ] = llm_payload
        return context

    def _query_llm(self, context: JobContext) -> Optional[Dict[str, Any]]:
        description = context.description or ""
        summary = json.dumps(
            {
                "url": context.url,
                "current_title": context.title,
                "current_company": context.company,
                "team_hint": context.meta.get("job_role"),
                "verified_domain": context.meta.get("source_domain"),
                "description": description,
            },
            ensure_ascii=False,
        )

        response = structured_chat(
            summary,
            system_prompt=self._PROMPT_TEMPLATE,
            model="mistral-small-latest",
            temperature=0.1,
            max_tokens=600,
        )
        if response and isinstance(response, dict):
            return response
        logger.debug("InformationExtractionAgent received no usable LLM response")
        return None

    def _build_profile(
        self, context: JobContext, llm_payload: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        profile = {
            "url": context.url,
            "job_title": context.title,
            "company": context.company,
            "team": None,
            "location": context.meta.get("location"),
            "experience_required": None,
            "education_required": None,
            "skills": [],
            "job_type": None,
            "verified_domain": context.meta.get("source_domain"),
            "authenticity_score": None,
            "scraped_at": context.meta.get("scraped_at"),
        }

        if llm_payload:
            profile.update(
                {
                    key: llm_payload.get(key)
                    for key in (
                        "url",
                        "job_title",
                        "company",
                        "team",
                        "location",
                        "experience_required",
                        "education_required",
                        "job_type",
                        "verified_domain",
                        "authenticity_score",
                    )
                    if llm_payload.get(key) is not None
                }
            )
            skills = llm_payload.get("skills")
            if isinstance(skills, list):
                profile["skills"] = [str(item) for item in skills if isinstance(item, str)]

        # Ensure defaults for critical fields
        if profile.get("authenticity_score") is None:
            profile["authenticity_score"] = 0.0
        profile.setdefault("skills", [])

        # Update context title/company if LLM supplied better versions
        if profile.get("job_title"):
            context.title = profile["job_title"]
        if profile.get("company"):
            context.company = profile["company"]

        return profile
