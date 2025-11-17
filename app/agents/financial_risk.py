from __future__ import annotations

import re

from app.utils import FINANCIAL_RED_FLAGS, SENSITIVE_INFO_FLAGS

from .base import Agent, JobContext


class FinancialRiskAgent(Agent):
    """Evaluates monetary claims and sensitive information requests."""

    name = "financial_risk"

    def run(self, context: JobContext) -> JobContext:
        text = (context.description or "").lower()
        for phrase in FINANCIAL_RED_FLAGS:
            if phrase in text:
                context.add_flag("financial", f"Financial red flag: {phrase}")
        for phrase in SENSITIVE_INFO_FLAGS:
            if phrase in text:
                context.add_flag("financial", f"Requests sensitive information: {phrase}")

        salary_signals = self._score_salary_expectations(context)
        for signal in salary_signals:
            context.add_flag("financial", signal)

        flagged_count = len(context.flags.get("financial", []))
        context.meta["financial_score"] = max(0, 100 - flagged_count * 18)
        return context

    @staticmethod
    def _score_salary_expectations(context: JobContext) -> list[str]:
        signals: list[str] = []
        salary_mentions = context.salary_mentions
        if not salary_mentions:
            return signals
        numeric_values = []
        for mention in salary_mentions:
            digits = re.sub(r"[^0-9]", "", mention)
            if not digits:
                continue
            try:
                numeric_values.append(int(digits))
            except ValueError:
                continue
        if not numeric_values:
            return signals
        average_salary = sum(numeric_values) / len(numeric_values)
        role = str(context.meta.get("job_role", "")).lower()
        if role and average_salary > 200000 and any(word in role for word in ["assistant", "entry", "junior"]):
            signals.append("Salary claim far above typical range for role")
        if average_salary < 20000 and "full time" in (context.description or "").lower():
            signals.append("Salary claim well below typical full-time compensation")
        return signals
