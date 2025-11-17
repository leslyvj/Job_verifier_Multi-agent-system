from __future__ import annotations

from collections import Counter
from typing import Optional

from app.services.llm import chat, llm_available
from app.utils import CATEGORY_WEIGHTS, RISK_SYNTHESIS_SYSTEM_PROMPT

from .base import Agent, JobContext


class RiskSynthesisAgent(Agent):
    """Aggregates signals from all agents and produces a verdict."""

    name = "risk_synthesis"
    _LLM_SYSTEM_PROMPT = RISK_SYNTHESIS_SYSTEM_PROMPT

    def run(self, context: JobContext) -> JobContext:
        weighted_total = 0.0
        total_weight = 0.0
        flag_counter = Counter()

        # Check if scraping was incomplete on trusted domain
        is_trusted = context.meta.get("trusted_domain", False)
        scraping_incomplete = context.meta.get("scraping_incomplete", False)

        for category, weight in CATEGORY_WEIGHTS.items():
            flag_count = len(context.flags.get(category, []))
            flag_counter[category] = flag_count

            # Further reduce weight of acquisition flags for trusted domains
            if category == "acquisition" and is_trusted:
                weight = 0.05  # Almost ignore acquisition issues on trusted sites

            weighted_total += flag_count * 15 * weight  # Reduced from 20
            total_weight += 15 * weight

        risk_score = min(100, round(weighted_total)) if total_weight else 0
        verdict = self._derive_verdict(risk_score, flag_counter, is_trusted, scraping_incomplete)

        # LLM sanity check - override if it disagrees strongly
        if llm_available() and verdict in ["fake", "suspicious"]:
            llm_verdict = self._llm_sanity_check(context, verdict, risk_score, flag_counter)
            if llm_verdict and llm_verdict != verdict:
                # Store original verdict in insights
                context.meta.setdefault("insights", {}).setdefault("risk_synthesis", {})[
                    "heuristic_verdict"
                ] = verdict
                verdict = llm_verdict

        confidence = max(0, min(100, 100 - risk_score))

        # Use .get() for all score fields to handle missing values gracefully
        content_score = context.meta.get("content_score", 75)
        verification_score = context.meta.get("verification_score", 75)
        financial_score = context.meta.get("financial_score", 100)

        context.meta.update(
            {
                "risk_score": risk_score,
                "confidence": confidence,
                "verdict": verdict,
                "flag_summary": dict(flag_counter),
                "content_score": content_score,
                "verification_score": verification_score,
                "financial_score": financial_score,
            }
        )

        narrative = self._llm_generate_summary(context, risk_score, verdict)
        if narrative:
            context.meta.setdefault("insights", {})["risk_summary"] = narrative
        return context

    @staticmethod
    def _derive_verdict(
        risk_score: int,
        flag_counter: Counter,
        is_trusted: bool,
        scraping_incomplete: bool,
    ) -> str:
        # If scraping failed on trusted domain, can't make determination
        if is_trusted and scraping_incomplete:
            acquisition_flags = flag_counter.get("acquisition", 0)
            other_flags = flag_counter.total() - acquisition_flags

            if other_flags == 0:
                return "incomplete_data"  # Only acquisition flags on trusted site

        # Much stricter thresholds to reduce false positives
        financial_flags = flag_counter.get("financial", 0)
        content_flags = flag_counter.get("content", 0)

        # Only flag as fake if EXTREME evidence
        if financial_flags >= 3:  # Multiple serious financial red flags
            return "fake"
        if risk_score >= 85:  # Very high risk score
            return "fake"

        # Suspicious requires moderate evidence
        if risk_score >= 60 or (financial_flags >= 2 and content_flags >= 2):
            return "suspicious"

        # Default to legit unless strong evidence of scam
        return "legit"

    def _llm_sanity_check(
        self, context: JobContext, heuristic_verdict: str, risk_score: int, flag_counter: Counter
    ) -> Optional[str]:
        """Ask LLM to review the verdict and override if it's a false positive."""
        flags = context.flags
        flag_lines = []
        for category, entries in flags.items():
            if not entries:
                continue
            preview = "; ".join(entries[:5])
            flag_lines.append(f"{category}: {preview}")
        flag_text = " | ".join(flag_lines) if flag_lines else "no flags"

        prompt = (
            "Review this job posting fraud assessment. The heuristic system flagged it as potentially fraudulent, "
            "but we need your expert opinion to avoid false positives.\n\n"
            f"Job Title: {context.title or 'Unknown'}\n"
            f"Company: {context.company or 'Unknown'}\n"
            f"Source Domain: {context.meta.get('source_domain', 'Unknown')}\n"
            f"Heuristic Verdict: {heuristic_verdict}\n"
            f"Risk Score: {risk_score}/100\n"
            f"Flags Raised: {flag_text}\n\n"
            "Question: Is this job posting ACTUALLY a scam, or could it be legitimate?\n\n"
            "Consider:\n"
            "- Are the flags contextually reasonable for this company/industry?\n"
            "- Could this be a legitimate job with poorly worded description?\n"
            "- Are we over-reacting to common phrases?\n\n"
            "Respond with ONLY ONE WORD:\n"
            "- 'fake' if you're confident it's a scam\n"
            "- 'suspicious' if you're unsure but concerned\n"
            "- 'legit' if you believe it's legitimate despite the flags"
        )

        response = chat(
            prompt,
            system_prompt=(
                "You are a senior fraud analyst. Avoid false positives. Many legitimate jobs have features "
                "that could seem suspicious in isolation. Be skeptical but fair."
            ),
            model="mistral-small-latest",
            max_tokens=50,
            temperature=0.1,
        )

        if response:
            response_lower = response.strip().lower()
            if "legit" in response_lower:
                return "legit"
            elif "suspicious" in response_lower:
                return "suspicious"
            elif "fake" in response_lower:
                return "fake"

        return None  # Keep original verdict if LLM unclear

    def _llm_generate_summary(
        self, context: JobContext, risk_score: int, verdict: str
    ) -> Optional[str]:
        flags = context.flags
        flag_lines = []
        for category, entries in flags.items():
            if not entries:
                continue
            preview = "; ".join(entries[:3])
            flag_lines.append(f"{category}: {preview}")
        flag_text = " | ".join(flag_lines) if flag_lines else "no major flags"
        prompt = (
            "Produce a short user-facing summary of the investigation outcome.\n"
            f"Verdict: {verdict}\n"
            f"Risk score: {risk_score}\n"
            f"Key signals: {flag_text}\n"
            "Close with a next-step recommendation tailored to the verdict."
        )
        summary = chat(
            prompt,
            system_prompt=self._LLM_SYSTEM_PROMPT,
            model="mistral-small-latest",
            max_tokens=200,
        )
        return summary
