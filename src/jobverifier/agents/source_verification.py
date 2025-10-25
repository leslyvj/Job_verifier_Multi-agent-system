from __future__ import annotations

from urllib.parse import urlparse

from .base import Agent, JobContext

GENERIC_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "protonmail.com",
}

SUSPICIOUS_TLDS = {"xyz", "top", "store", "site", "click", "info"}


class SourceVerificationAgent(Agent):
    """Validates source credibility using lightweight heuristics."""

    name = "source_verification"

    def run(self, context: JobContext) -> JobContext:
        domain = urlparse(context.url).netloc.lower()
        email_domains = {email.split("@")[-1] for email in context.contact_emails}
        no_email_expected = bool(context.meta.get("no_email_expected"))

        if not email_domains:
            if no_email_expected:
                context.meta.setdefault("insights", {}).setdefault(
                    "source_verification", {}
                )["note"] = "No contact email expected for this platform"
            else:
            # Less severe if it's a major platform (they often don't list emails)
                if any(platform in domain for platform in ["linkedin.com", "indeed.com", "glassdoor.com", "oraclecloud.com", "oracle.com", "workday.com"]):
                    context.meta.setdefault("insights", {}).setdefault(
                        "source_verification", {}
                    )["note"] = "Platform typically hides recruiter emails"
                else:
                    context.add_flag("verification", "No contact email found in posting")
        else:
            for email_domain in email_domains:
                if email_domain in GENERIC_EMAIL_DOMAINS:
                    context.add_flag(
                        "verification",
                        f"Contact email uses generic domain: {email_domain}",
                    )
                elif email_domain.split(".")[-1] in SUSPICIOUS_TLDS:
                    context.add_flag(
                        "verification",
                        f"Email domain uses uncommon TLD: {email_domain}",
                    )
                elif email_domain not in domain:
                    context.add_flag(
                        "verification",
                        f"Contact email domain {email_domain} differs from source domain {domain}",
                    )

        if context.company and context.company.lower() in {"company not found", "unknown"}:
            context.add_flag("verification", "Company name is missing or generic")

        for channel in context.contact_channels:
            context.add_flag(
                "verification",
                f"Job relies on consumer messaging app: {channel}",
            )

        flagged_count = len(context.flags.get("verification", []))
        score = max(0, 100 - flagged_count * 20)
        context.meta["verification_score"] = score
        return context
