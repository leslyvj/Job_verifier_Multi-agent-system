from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

from app.services.llm import llm_available, structured_chat
from app.utils import (
    CONTENT_ANALYSIS_SYSTEM_PROMPT,
    CRITICAL_FINANCIAL_FLAGS,
    EXTREME_SCAM_PHRASES,
)

from .base import Agent, JobContext


class ContentAnalysisAgent(Agent):
    """Evaluates text quality, financial risk patterns, and extracts structured content signals using LLM-first approach."""

    name = "content_analysis"
    _LLM_SYSTEM_PROMPT = CONTENT_ANALYSIS_SYSTEM_PROMPT

    def run(self, context: JobContext) -> JobContext:
        text = context.trimmed_description or ""
        tokens = text.split()
        context.meta["content_token_count"] = len(tokens)
        context.meta["job_role"] = self._extract_job_role(context.title)

        if context.meta.get("scraping_incomplete"):
            insight = context.meta.setdefault("insights", {}).setdefault(
                "content_analysis", {}
            )
            insight["note"] = "Content analysis skipped due to incomplete scrape"
            context.meta["content_score"] = 100  # Don't penalize for scraping issues
            context.meta["financial_score"] = 100
            return context

        if not text:
            context.add_flag("content", "Job description missing or empty")
            context.meta["content_score"] = 50  # Neutral score, not failure
            context.meta["financial_score"] = 100
            return context

        # LLM-first analysis - primary intelligence
        llm_feedback = self._llm_review_content(context.title, text, context)

        if llm_feedback:
            self._process_llm_feedback(context, llm_feedback)
        else:
            # LLM unavailable - use minimal heuristics only
            context.meta.setdefault("insights", {}).setdefault(
                "content_analysis", {}
            )["note"] = "LLM unavailable; using basic heuristics"
            self._fallback_analysis(context, text)

        return context

    def _llm_review_content(
        self, title: Optional[str], description: str, context: JobContext
    ) -> Optional[Dict[str, object]]:
        """Primary LLM-based content analysis with context awareness."""
        if not llm_available():
            return None

        company = context.company or "Unknown"
        source_domain = context.meta.get("source_domain", "Unknown")

        prompt = (
            "Analyze this job posting for fraud indicators. Consider the full context before flagging.\n\n"
            "LEGITIMATE features you should NOT flag:\n"
            "- 'Work from home' or 'remote' (common for tech/modern jobs)\n"
            "- 'No experience required' (legitimate for entry-level)\n"
            "- Mentioning training programs (normal for many companies)\n"
            "- Crypto/blockchain jobs (legitimate industry)\n"
            "- Asking for standard background checks or references\n\n"
            "ACTUAL red flags (flag only if MULTIPLE present or EXTREME):\n"
            "- Requests to send money, gift cards, or wire transfers UPFRONT\n"
            "- Asking for SSN/bank info BEFORE interview/offer\n"
            "- Guaranteed income with no work described\n"
            "- Extreme urgency ('act now', 'limited slots') + vague job description\n"
            "- Grammar/spelling errors + unrealistic promises\n\n"
            f"Company: {company}\n"
            f"Source Domain: {source_domain}\n"
            f"Job Title: {title or 'Unknown'}\n"
            f"Description:\n{description[:4000]}\n\n"
            "Return JSON with:\n"
            "- content_score (0-100, where 100=perfect, 50=neutral, 0=extreme scam)\n"
            "- financial_score (0-100, based on money scam patterns only)\n"
            "- risk_flags (array of specific concerns, empty if legit)\n"
            "- pii_flags (array of inappropriate data requests, empty if none)\n"
            "- summary (brief assessment)\n"
            "- confidence (0-100, your confidence in this assessment)"
        )

        response = structured_chat(
            prompt,
            system_prompt=self._LLM_SYSTEM_PROMPT,
            model="mistral-small-latest",
            max_tokens=500,
            temperature=0.1,  # Lower temperature for consistency
        )

        return response if response and isinstance(response, dict) else None

    def _process_llm_feedback(self, context: JobContext, feedback: Dict[str, object]) -> None:
        """Process LLM feedback and update context."""
        insights = context.meta.setdefault("insights", {}).setdefault("content_analysis", {})

        # Store LLM assessment
        insights["llm_summary"] = feedback.get("summary", "")
        insights["llm_confidence"] = feedback.get("confidence", 50)

        # Set scores from LLM
        context.meta["content_score"] = max(0, min(100, int(feedback.get("content_score", 75))))
        context.meta["financial_score"] = max(0, min(100, int(feedback.get("financial_score", 100))))

        # Add flags only if LLM identified specific issues
        for flag in feedback.get("risk_flags", []) or []:
            if flag and isinstance(flag, str):
                context.add_flag("content", flag)

        for flag in feedback.get("pii_flags", []) or []:
            if flag and isinstance(flag, str):
                context.add_flag("financial", f"Inappropriate data request: {flag}")

        # Only check extreme scam phrases if LLM had concerns
        if context.meta["content_score"] < 60 or context.meta["financial_score"] < 60:
            self._check_extreme_patterns(context)

    def _fallback_analysis(self, context: JobContext, text: str) -> None:
        """Minimal fallback when LLM is unavailable - very conservative."""
        lower_text = text.lower()

        # Only check for EXTREME scam patterns
        extreme_found = False
        for phrase in EXTREME_SCAM_PHRASES:
            if phrase in lower_text:
                context.add_flag("content", f"Critical scam phrase: {phrase}")
                extreme_found = True

        for phrase in CRITICAL_FINANCIAL_FLAGS:
            if phrase in lower_text:
                context.add_flag("financial", f"Critical financial scam: {phrase}")
                extreme_found = True

        # Very lenient scoring without LLM
        if extreme_found:
            context.meta["content_score"] = 30
            context.meta["financial_score"] = 20
        else:
            context.meta["content_score"] = 75  # Assume legitimate
            context.meta["financial_score"] = 90

    def _check_extreme_patterns(self, context: JobContext) -> None:
        """Double-check for extreme scam patterns when LLM has concerns."""
        text = (context.trimmed_description or "").lower()

        for phrase in EXTREME_SCAM_PHRASES:
            if phrase in text:
                context.add_flag("content", f"Extreme scam indicator: {phrase}")

        for phrase in CRITICAL_FINANCIAL_FLAGS:
            if phrase in text:
                context.add_flag("financial", f"Extreme financial scam: {phrase}")

    @staticmethod
    def _extract_job_role(title: str | None) -> str:
        if not title:
            return "Unknown Role"
        normalized = re.sub(r"\s+\|.*$", "", title)
        normalized = re.sub(r"\s+-\s+.*$", "", normalized)
        return normalized.strip() or "Unknown Role"
