from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

from ..services.llm import structured_chat
from .base import Agent, JobContext

COMMON_SUSPICIOUS_PHRASES = [
    "no experience",
    "work from home",
    "quick money",
    "cash daily",
    "guaranteed income",
    "start today",
    "limited slots",
    "training fee",
]

POOR_LANGUAGE_INDICATORS = ["??", "!!!", "???", "!!!", "--", "@@"]


class ContentAnalysisAgent(Agent):
    """Evaluates text quality and extracts structured content signals."""

    name = "content_analysis"
    _LLM_SYSTEM_PROMPT = (
        "You are an assistant that audits job postings for language quality, "
        "fraud risk signals, and exposure of personal data requests. "
        "Respond using compact JSON only."
    )

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
            context.meta["content_score"] = 0
            return context

        if not text:
            context.add_flag("content", "Job description missing or empty")
            context.meta["content_score"] = 0
            return context

        flags = self._evaluate_language_quality(text)
        for flag in flags:
            context.add_flag("content", flag)

        suspicious_phrases = self._find_suspicious_phrases(text)
        for phrase in suspicious_phrases:
            context.add_flag("content", f"Suspicious phrase detected: {phrase}")

        llm_feedback = self._llm_review_content(context.title, text)
        if llm_feedback:
            insights_bucket = context.meta.setdefault("insights", {}).setdefault(
                "content_analysis", {}
            )
            summary = llm_feedback.get("summary")
            if summary:
                insights_bucket["llm_summary"] = summary
            for flag in llm_feedback.get("risk_flags", []) or []:
                context.add_flag("content", flag)
            pii_mentions = llm_feedback.get("pii_mentions") or []
            for pii in pii_mentions:
                if pii:
                    context.add_flag("content", f"PII request noted: {pii}")
            if pii_mentions:
                insights_bucket["pii_mentions"] = pii_mentions

        score = self._score_content(len(tokens), flags, suspicious_phrases)
        context.meta["content_score"] = score
        return context

    def _llm_review_content(
        self, title: Optional[str], description: str
    ) -> Optional[Dict[str, object]]:
        prompt = (
            "Evaluate the following job posting content for warning signs.\n"
            "Return JSON with keys: summary (string), risk_flags (array of short strings), "
            "pii_mentions (array of short strings describing any requests for sensitive data).\n"
            "Focus on language quality issues, unrealistic offers, pressure tactics, or personal data requests.\n"
            f"Job title: {title or 'Unknown'}\n"
            f"Description:\n{description[:4000]}"
        )
        response = structured_chat(
            prompt,
            system_prompt=self._LLM_SYSTEM_PROMPT,
            model="mistral-small-latest",
            max_tokens=400,
        )
        if response and isinstance(response, dict):
            return response
        return None

    @staticmethod
    def _extract_job_role(title: str | None) -> str:
        if not title:
            return "Unknown Role"
        normalized = re.sub(r"\s+\|.*$", "", title)
        normalized = re.sub(r"\s+-\s+.*$", "", normalized)
        return normalized.strip() or "Unknown Role"

    @staticmethod
    def _evaluate_language_quality(text: str) -> List[str]:
        flags: List[str] = []
        sentences = [seg.strip() for seg in re.split(r"[.!?]", text) if seg.strip()]
        average_sentence_length = (
            sum(len(sentence.split()) for sentence in sentences) / len(sentences)
            if sentences
            else 0
        )
        if average_sentence_length < 7:
            flags.append("Very short sentences suggest low-quality copy")
        uppercase_ratio = sum(1 for ch in text if ch.isupper()) / max(len(text), 1)
        if uppercase_ratio > 0.25:
            flags.append("Excessive uppercase usage")
        punctuation_noise = sum(text.count(token) for token in POOR_LANGUAGE_INDICATORS)
        if punctuation_noise:
            flags.append("Noisy punctuation patterns detected")
        return flags

    @staticmethod
    def _find_suspicious_phrases(text: str) -> List[str]:
        lower_text = text.lower()
        return [phrase for phrase in COMMON_SUSPICIOUS_PHRASES if phrase in lower_text]

    @staticmethod
    def _score_content(token_count: int, flags: List[str], phrases: List[str]) -> int:
        base_score = 100
        penalty = 0
        penalty += len(flags) * 15
        penalty += len(phrases) * 10
        if token_count < 80:
            penalty += 10
        if token_count > 600:
            penalty += 5
        return max(0, math.floor(base_score - penalty))
