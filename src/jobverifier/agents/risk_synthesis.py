from __future__ import annotations

from collections import Counter
from typing import Optional

from ..services.llm import chat
from .base import Agent, JobContext

CATEGORY_WEIGHTS = {
    "acquisition": 0.3,  # Reduced: scraping issues != scam indicators
    "content": 1.1,
    "verification": 1.3,
    "financial": 1.6,
    "intelligence": 0.9,
}


class RiskSynthesisAgent(Agent):
    """Aggregates signals from all agents and produces a verdict."""

    name = "risk_synthesis"
    _LLM_SYSTEM_PROMPT = (
        "You summarize job posting investigations, balancing caution with clarity. "
        "Respond with two concise sentences."
    )

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
                weight = 0.1  # Almost ignore acquisition issues on trusted sites
            
            weighted_total += flag_count * 20 * weight
            total_weight += 20 * weight

        risk_score = min(100, round(weighted_total)) if total_weight else 0
        verdict = self._derive_verdict(risk_score, flag_counter, is_trusted, scraping_incomplete)
        confidence = max(0, 100 - risk_score)

        context.meta.update(
            {
                "risk_score": risk_score,
                "confidence": confidence,
                "verdict": verdict,
                "flag_summary": dict(flag_counter),
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
        scraping_incomplete: bool
    ) -> str:
        # If scraping failed on trusted domain, can't make determination
        if is_trusted and scraping_incomplete:
            acquisition_flags = flag_counter.get("acquisition", 0)
            other_flags = flag_counter.total() - acquisition_flags
            
            if other_flags == 0:
                return "incomplete_data"  # Only acquisition flags on trusted site
            # If there are content/financial red flags even on trusted site, still flag
        
        # Normal verdict logic
        if risk_score >= 70 or flag_counter.get("financial", 0) >= 2:
            return "fake"
        if risk_score >= 45 or flag_counter.total() >= 4:
            return "suspicious"
        return "legit"

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
