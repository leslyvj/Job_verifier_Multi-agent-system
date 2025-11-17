"""Diagnostic script to evaluate SourceVerificationAgent company checks."""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.agents import JobContext, SourceVerificationAgent

LOGGER = logging.getLogger("company_agent_check")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def build_context(company: str, domain: str, url: str) -> JobContext:
    """Create a JobContext seeded with basic company information."""
    context = JobContext(url=url)
    context.company = company or None
    context.meta["source_domain"] = domain or None
    context.meta["job_role"] = "Diagnostic Run"
    context.contact_emails = []
    context.contact_channels = []
    context.salary_mentions = []
    return context


def run_agent(company: str, domain: str, url: str) -> Tuple[Optional[JobContext], Optional[str]]:
    """Execute SourceVerificationAgent and return updated context."""
    context = build_context(company, domain, url)
    agent = SourceVerificationAgent()

    try:
        context = agent.run(context)
        return context, None
    except Exception as exc:  # pragma: no cover - diagnostics should never crash
        return None, str(exc)


def evaluate_capabilities(intel: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Assess which capabilities are implemented based on agent output."""
    checks: List[Tuple[str, bool, str]] = []

    domain_lookup = bool(intel.get("company_domain") or intel.get("inferred_domain"))
    domain_detail = (
        f"Domain detected: {intel.get('company_domain') or intel.get('inferred_domain')}"
        if domain_lookup
        else "No domain resolved from context"
    )
    checks.append(("Domain Lookup", domain_lookup, domain_detail))

    domain_age = intel.get("domain_age")
    checks.append(
        (
            "Domain Age",
            bool(domain_age),
            f"Domain age reported as {domain_age}" if domain_age else "Domain age lookup not implemented",
        )
    )

    web_presence_status = intel.get("web_presence_status")
    if web_presence_status == "found":
        sources = intel.get("web_presence", [])
        summary = f"Web sources gathered: {len(sources)}"
    elif web_presence_status:
        summary = f"Web presence status: {web_presence_status}"
    else:
        summary = "Web presence lookup not executed"
    checks.append(("Web Presence", web_presence_status == "found", summary))

    press_mentions = intel.get("press_mentions")
    press_detail = (
        f"Press mentions found: {len(press_mentions)}" if isinstance(press_mentions, list)
        else "Press mention search not executed"
    )
    checks.append(("Press Mentions", isinstance(press_mentions, list), press_detail))

    hr_contacts = intel.get("hr_contacts")
    hr_detail = (
        f"HR contacts discovered: {len(hr_contacts)}"
        if isinstance(hr_contacts, list)
        else "HR contact discovery not executed"
    )
    checks.append(("HR / Contact Info", isinstance(hr_contacts, list), hr_detail))

    team_links = intel.get("team_links")
    team_detail = (
        f"Team links detected: {len(team_links)}" if isinstance(team_links, list)
        else "Team/leadership page probing not executed"
    )
    checks.append(("Team Links", isinstance(team_links, list), team_detail))

    filings = intel.get("recent_filings")
    filings_detail = (
        "Recent regulatory filings detected" if filings
        else "No regulatory filings found or SEC lookup unavailable"
    )
    checks.append(("Regulatory Filings", filings is not None, filings_detail))

    legitimacy_score = intel.get("legitimacy_score")
    score_detail = (
        f"Legitimacy score: {legitimacy_score}/100" if legitimacy_score is not None
        else "Legitimacy scoring not available"
    )
    checks.append(("Reputation Score", legitimacy_score is not None, score_detail))

    results: List[Dict[str, Any]] = []
    for label, status, detail in checks:
        icon = "✅ PASS" if status else "❌ MISSING"
        LOGGER.info("%s — %s", icon, label)
        LOGGER.info("   %s", detail)
        results.append(
            {
                "label": label,
                "status": "pass" if status else "missing",
                "detail": detail,
            }
        )
    return results


def write_report(
    path: Path,
    company: str,
    domain: str,
    url: str,
    capabilities: List[Dict[str, Any]],
    intel: Dict[str, Any],
    flags: Dict[str, List[str]],
    error: Optional[str],
) -> None:
    """Persist diagnostic results as JSON."""
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "company": company,
        "domain": domain,
        "url": url,
        "error": error,
        "capabilities": capabilities,
        "flags": flags,
        "intel": intel,
    }
    path.write_text(json.dumps(report, indent=2, sort_keys=True))
    LOGGER.info("📝 Report written to %s", path)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Check SourceVerificationAgent capabilities.")
    parser.add_argument("--company", default="", help="Company name to evaluate")
    parser.add_argument("--domain", default="", help="Company domain (e.g., example.com)")
    parser.add_argument(
        "--url",
        default="",
        help="Job posting URL (defaults to https://<domain>/ if domain is provided)",
    )
    parser.add_argument(
        "--output",
        default="company_agent_check_report.json",
        help="Path for the JSON diagnostics report",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for CLI execution."""
    args = parse_args()
    url = args.url or (f"https://{args.domain}/" if args.domain else "https://example.com/job")
    LOGGER.info("🔍 Running SourceVerificationAgent diagnostics")
    LOGGER.info("   Company: %s", args.company or "N/A")
    LOGGER.info("   Domain:  %s", args.domain or "N/A")
    LOGGER.info("   URL:     %s", url)

    context, error = run_agent(args.company, args.domain, url)
    if error:
        LOGGER.error("❌ Agent execution failed: %s", error)
        write_report(
            Path(args.output),
            args.company,
            args.domain,
            url,
            [],
            {},
            {},
            error,
        )
        return

    intel = context.meta.get("company_intel", {}) if context else {}
    flags = context.flags if context else {}

    LOGGER.info("------------------------------------------------------------")
    LOGGER.info("📋 Capability Checks")
    LOGGER.info("------------------------------------------------------------")
    capabilities = evaluate_capabilities(intel)

    passed = sum(1 for item in capabilities if item["status"] == "pass")
    missing = len(capabilities) - passed
    LOGGER.info("------------------------------------------------------------")
    LOGGER.info("✅ Capabilities implemented: %d", passed)
    LOGGER.info("❌ Capabilities missing:     %d", missing)

    write_report(
        Path(args.output),
        args.company,
        args.domain,
        url,
        capabilities,
        intel,
        flags,
        error,
    )


if __name__ == "__main__":
    main()