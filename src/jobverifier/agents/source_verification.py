from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

from ..services import llm_available, structured_chat
from .base import Agent, JobContext
from .data_acquisition import TRUSTED_DOMAINS

try:  # Playwright is optional
    from playwright.sync_api import sync_playwright  # type: ignore[import]
    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover - environment without playwright
    PLAYWRIGHT_AVAILABLE = False

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DUCKDUCKGO_HTML = "https://duckduckgo.com/html/"
PRESS_QUERY_TEMPLATE = "{company} press release"
EMPLOYEE_QUERY_TEMPLATE = 'site:linkedin.com/in "{company}" ({keywords})'

GENERIC_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "protonmail.com",
    "icloud.com",
}

SUSPICIOUS_TLDS = {"xyz", "top", "store", "site", "click", "info"}

TRUSTED_ENTERPRISE_SUFFIXES = {
    "amazon.com",
    "amazon.jobs",
    "google.com",
    "alphabet.com",
    "microsoft.com",
    "apple.com",
    "meta.com",
    "linkedin.com",
    "oracle.com",
    "oraclecloud.com",
    "workday.com",
    "salesforce.com",
    "indeed.com",
    "glassdoor.com",
}

JOB_BOARD_DOMAINS = {
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "monster.com",
    "careerbuilder.com",
    "ziprecruiter.com",
    "lever.co",
    "greenhouse.io",
    "workday.com",
}

TRUSTED_BRAND_KEYWORDS = {
    "amazon",
    "google",
    "microsoft",
    "apple",
    "netflix",
    "meta",
    "linkedin",
    "indeed",
    "glassdoor",
    "monster",
    "ziprecruiter",
    "careerbuilder",
    "oracle",
}

logger = logging.getLogger(__name__)


@dataclass
class LinkedInProfile:
    url: str
    followers: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[str] = None


class SourceVerificationAgent(Agent):
    """Validates source credibility using heuristics and company intelligence gathering."""

    name = "source_verification"

    def __init__(self, request_timeout: int = 10) -> None:
        self.request_timeout = request_timeout

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

        # Company intelligence gathering (merged from CompanyIntelligenceAgent)
        self._gather_company_intelligence(context)

        return context

    def _gather_company_intelligence(self, context: JobContext) -> None:
        """Gather company intelligence using OSINT (merged from CompanyIntelligenceAgent)."""
        company_name = (context.company or "").strip()
        source_domain = str(context.meta.get("source_domain") or "")
        job_role = str(context.meta.get("job_role") or context.title or "").strip()

        inferred_domain = self._infer_company_domain(context)
        normalised_domain = self._normalise_domain(inferred_domain or source_domain)

        intel: Dict[str, Any] = {
            "company_name": company_name or None,
            "source_domain": source_domain or None,
            "inferred_domain": inferred_domain,
            "company_domain": normalised_domain,
            "job_role": job_role or None,
        }

        llm_ready = llm_available()

        is_trusted = bool(context.meta.get("trusted_domain"))
        domain_candidate = (normalised_domain or inferred_domain or source_domain or "").lower()
        if not is_trusted and domain_candidate:
            if any(domain_candidate.endswith(suffix) for suffix in TRUSTED_ENTERPRISE_SUFFIXES):
                is_trusted = True
            elif any(trusted in domain_candidate for trusted in TRUSTED_DOMAINS):
                is_trusted = True
        if not is_trusted and company_name:
            lowered_company = company_name.lower()
            if any(keyword in lowered_company for keyword in TRUSTED_BRAND_KEYWORDS):
                is_trusted = True

        intel["trusted_inference"] = is_trusted

        if not domain_candidate and not company_name:
            context.add_flag(
                "intelligence",
                "No company identifiers available for open-source checks",
            )
            context.meta["company_intel"] = intel
            context.meta.setdefault("insights", {})["company_intelligence"] = intel
            return

        if not normalised_domain and not is_trusted:
            context.add_flag(
                "intelligence",
                "Unable to determine official company domain from posting",
            )

        site_probe = self._probe_official_pages(normalised_domain, company_name)
        intel["team_links"] = site_probe["team_links"]
        intel["press_mentions"] = site_probe["press_mentions"]

        linkedin_info = self._fetch_linkedin_profile(company_name)
        if linkedin_info:
            intel["linkedin_profile"] = linkedin_info.__dict__
            intel["linkedin_profile_status"] = "present"
        else:
            intel["linkedin_profile"] = None
            intel["linkedin_profile_status"] = "not_accessible" if is_trusted else "not_found"
            if not is_trusted:
                context.add_flag(
                    "intelligence",
                    "LinkedIn company profile not found or inaccessible",
                )

        hr_contacts = self._discover_hr_contacts(company_name, normalised_domain, job_role)
        if llm_ready:
            refined_contacts = self._refine_contacts_with_llm(company_name, normalised_domain, hr_contacts)
            if refined_contacts is not None:
                hr_contacts = refined_contacts
        intel["hr_contacts"] = hr_contacts
        if not hr_contacts:
            if is_trusted:
                intel["hr_contacts_status"] = "not_visible"
            else:
                context.add_flag(
                    "intelligence",
                    "No HR or recruiting contacts surfaced in public search",
                )

        has_filings = self._has_recent_filings(company_name)
        intel["recent_filings"] = has_filings

        legitimacy_score = self._score_legitimacy(
            normalised_domain,
            is_trusted,
            linkedin_info,
            hr_contacts,
            len(site_probe["press_mentions"]),
            len(site_probe["team_links"]),
            has_filings,
        )
        intel["legitimacy_score"] = legitimacy_score

        if llm_ready:
            llm_assessment = self._llm_assess_company(intel, is_trusted)
            if llm_assessment:
                intel["llm_summary"] = llm_assessment.get("summary")
                intel["llm_confidence"] = llm_assessment.get("confidence")
                for alert in llm_assessment.get("alerts") or []:
                    context.add_flag("intelligence", alert)

        context.meta["company_intel"] = intel
        context.meta.setdefault("insights", {})["company_intelligence"] = intel

        if not is_trusted and legitimacy_score < 40:
            context.add_flag(
                "intelligence",
                "Company has weak online presence based on open-source checks",
            )

    # Company intelligence helper methods (from CompanyIntelligenceAgent)

    def _refine_contacts_with_llm(
        self,
        company_name: str,
        domain: Optional[str],
        contacts: List[Dict[str, str]],
    ) -> Optional[List[Dict[str, str]]]:
        if not contacts:
            return None

        prompt_payload = {
            "company": company_name,
            "domain": domain,
            "contacts": contacts,
        }
        prompt = (
            "Filter the provided contacts to genuine HR or recruiting individuals. "
            "Prefer linkedin.com/in profiles and drop job board ads or spam. "
            "Return JSON with a 'contacts' array, each entry containing name, role, profile.\n"
            f"Data: {json.dumps(prompt_payload, ensure_ascii=True)}"
        )
        response = structured_chat(
            prompt,
            system_prompt=(
                "You clean OSINT lead lists for recruiting outreach. Output compact JSON only."
            ),
            model="mistral-small-latest",
            max_tokens=350,
        )
        if not response or not isinstance(response, dict):
            logger.debug("LLM contact refinement skipped or returned empty result")
            return None

        clean_contacts: List[Dict[str, str]] = []
        for entry in response.get("contacts", []):
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            profile = entry.get("profile", "")
            role = entry.get("role", "")
            if not name or not profile:
                continue
            profile_lower = profile.lower()
            if "linkedin.com" not in profile_lower:
                if domain and domain.lower() not in profile_lower:
                    continue
            clean_contacts.append(
                {
                    "name": name.strip(),
                    "role": role.strip(),
                    "profile": profile.strip(),
                }
            )
        if clean_contacts:
            return clean_contacts[:5]
        return []

    def _probe_official_pages(
        self, domain: Optional[str], company_name: str
    ) -> Dict[str, List[str]]:
        team_links: List[str] = []
        press_links: List[str] = []

        if domain:
            candidate_paths = [
                f"https://{domain}/careers",
                f"https://{domain}/career",
                f"https://{domain}/jobs",
                f"https://{domain}/about",
                f"https://{domain}/company",
            ]
            for url in candidate_paths:
                html = self._safe_fetch(url)
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")
                heading = soup.find(["h1", "h2"], string=re.compile(r"careers|jobs|about|team", re.I))
                if heading:
                    team_links.append(url)
                    break

        if company_name:
            press_query = PRESS_QUERY_TEMPLATE.format(company=company_name)
            press_results = self._duckduckgo_results(press_query, max_results=5)
            press_links = [item["url"] for item in press_results if item.get("url")]

        return {"team_links": team_links, "press_mentions": press_links}

    def _duckduckgo_results(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        try:
            response = requests.post(
                DUCKDUCKGO_HTML,
                data={"q": query},
                headers={"User-Agent": USER_AGENT},
                timeout=self.request_timeout,
            )
            response.raise_for_status()
        except requests.RequestException:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results: List[Dict[str, str]] = []
        for result in soup.select("div.result"):
            classes = result.get("class", [])
            if any("result--ad" in cls for cls in classes):
                continue
            link = result.select_one("a.result__a")
            if not link:
                continue
            href = link.get("href", "")
            if "duckduckgo.com/y.js" in href:
                continue
            resolved = self._resolve_duckduckgo_redirect(href)
            if not resolved or "duckduckgo.com" in resolved:
                continue
            snippet_el = result.select_one(".result__snippet") or result.select_one("a.result__snippet")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append(
                {
                    "title": link.get_text(strip=True),
                    "url": resolved,
                    "snippet": snippet,
                }
            )
            if len(results) >= max_results:
                break
        return results

    @staticmethod
    def _resolve_duckduckgo_redirect(href: str) -> str:
        if not href:
            return ""
        if href.startswith("//"):
            href = "https:" + href
        if "duckduckgo.com/l/?" in href and "uddg=" in href:
            href = href.split("uddg=", 1)[1]
            href = href.split("&", 1)[0]
        return unquote(href)

    def _safe_fetch(self, url: str) -> Optional[str]:
        if not url:
            return None
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=self.request_timeout)
            if response.status_code >= 400:
                return None
            return response.text
        except requests.RequestException:
            return None

    def _has_recent_filings(self, company_name: str) -> bool:
        if not company_name:
            return False
        try:
            response = requests.get(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                params={
                    "company": company_name,
                    "owner": "exclude",
                    "action": "getcompany",
                    "count": "10",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=self.request_timeout,
            )
            if response.status_code >= 400:
                return False
            return "No matching" not in response.text
        except requests.RequestException:
            return False

    @staticmethod
    def _normalise_domain(domain: Optional[str]) -> Optional[str]:
        if not domain:
            return None
        lowered = domain.lower().lstrip("www.")
        parts = lowered.split(".")
        if len(parts) <= 2:
            return lowered
        return ".".join(parts[-2:])

    def _infer_company_domain(self, context: JobContext) -> Optional[str]:
        # 1. Inspect contact emails
        for email in context.contact_emails:
            if "@" not in email:
                continue
            domain = email.split("@")[-1].lower()
            if domain not in GENERIC_EMAIL_DOMAINS and "." in domain:
                return domain

        # 2. Use posting source domain if not a job board
        source_domain = context.meta.get("source_domain")
        if source_domain and not any(board in source_domain for board in JOB_BOARD_DOMAINS):
            return source_domain.lower()

        # 3. Attempt to search for official site via DuckDuckGo
        company = (context.company or "").strip()
        if not company:
            return None
        query = f"{company} official site"
        html = self._duckduckgo_search(query)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.select("a.result__a"):
            href = link.get("href", "")
            parsed = urlparse(href)
            hostname = parsed.netloc.lower()
            if hostname and not any(board in hostname for board in JOB_BOARD_DOMAINS):
                return hostname
        return None

    def _fetch_linkedin_profile(self, company_name: str) -> Optional[LinkedInProfile]:
        if not company_name:
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
        if not slug:
            return None

        base_url = f"https://www.linkedin.com/company/{slug}"
        about_url = f"{base_url}/about/"
        html = self._fetch_url(about_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        followers = self._extract_text(soup, "span", {"class": re.compile("followers", re.I)})
        industry = self._extract_text(soup, "dd", {"class": re.compile("industry", re.I)})
        if not industry:
            industry = self._extract_text(soup, "span", {"class": re.compile("industry", re.I)})
        employee_count = self._extract_text(soup, "dd", {"class": re.compile("company-size", re.I)})

        # If everything empty, treat as unavailable
        if not any([followers, industry, employee_count]):
            return None

        return LinkedInProfile(
            url=base_url,
            followers=followers,
            industry=industry,
            employee_count=employee_count,
        )

    def _discover_hr_contacts(
        self,
        company_name: str,
        domain: Optional[str],
        job_role: str,
    ) -> List[Dict[str, str]]:
        if not company_name:
            return []

        keywords = ["talent acquisition", "recruiter", "hr director", "hiring manager"]
        role_hint = job_role.split(",")[0].strip()
        if role_hint and 2 <= len(role_hint.split()) <= 5:
            keywords.append(role_hint)
        keyword_clause = " OR ".join(f'"{kw}"' for kw in keywords)
        query = EMPLOYEE_QUERY_TEMPLATE.format(company=company_name, keywords=keyword_clause)
        if domain and domain not in JOB_BOARD_DOMAINS:
            query = f"{query} \"{domain.split('.', 1)[0]}\""

        results = self._duckduckgo_results(query, max_results=8)
        contacts: List[Dict[str, str]] = []
        for result in results:
            url = result.get("url", "")
            if "linkedin.com/in" not in url:
                continue
            title = result.get("title", "").split("|")[0].split(" - ")[0].strip()
            if not title or len(title.split()) > 5:
                continue
            snippet = result.get("snippet", "")
            contacts.append(
                {
                    "name": title,
                    "role": snippet,
                    "profile": url,
                }
            )
            if len(contacts) >= 5:
                break

        unique: Dict[str, Dict[str, str]] = {}
        for contact in contacts:
            unique[contact["name"].lower()] = contact
        return list(unique.values())

    def _duckduckgo_search(self, query: str) -> Optional[str]:
        try:
            response = requests.get(
                DUCKDUCKGO_HTML,
                params={"q": query},
                headers={"User-Agent": USER_AGENT},
                timeout=self.request_timeout,
            )
            if response.status_code == 200:
                return response.text
        except requests.RequestException:
            return None
        return None

    def _fetch_url(self, url: str) -> Optional[str]:
        headers = {"User-Agent": USER_AGENT}
        try:
            response = requests.get(url, headers=headers, timeout=self.request_timeout)
            if response.status_code == 200:
                return response.text
            if response.status_code in {401, 403, 999} and PLAYWRIGHT_AVAILABLE:
                return self._fetch_with_playwright(url)
        except requests.RequestException:
            if PLAYWRIGHT_AVAILABLE:
                return self._fetch_with_playwright(url)
        return None

    def _fetch_with_playwright(self, url: str) -> Optional[str]:  # pragma: no cover - network heavy
        if not PLAYWRIGHT_AVAILABLE:
            return None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_user_agent(USER_AGENT)
                page.goto(url, wait_until="networkidle", timeout=self.request_timeout * 1000)
                page.wait_for_timeout(1500)
                content = page.content()
                browser.close()
                return content
        except Exception:
            return None

    @staticmethod
    def _extract_text(
        soup: BeautifulSoup, tag: str, attrs: Dict[str, object]
    ) -> Optional[str]:
        element = soup.find(tag, attrs=attrs)
        if not element:
            return None
        text = element.get_text(strip=True)
        return text or None

    @staticmethod
    def _score_legitimacy(
        domain: Optional[str],
        is_trusted: bool,
        linkedin: Optional[LinkedInProfile],
        contacts: List[Dict[str, str]],
        press_count: int,
        team_link_count: int,
        has_filings: bool,
    ) -> int:
        score = 40 if is_trusted else 25
        if domain:
            score += 15
        if linkedin:
            score += 20
        elif is_trusted:
            score += 10
        if contacts:
            score += min(20, 5 * len(contacts))
        elif is_trusted:
            score += 5
        score += min(10, press_count * 3)
        score += min(10, team_link_count * 5)
        if has_filings:
            score += 10
        return max(0, min(100, score))

    def _llm_assess_company(
        self,
        intel: Dict[str, Any],
        is_trusted: bool,
    ) -> Optional[Dict[str, object]]:
        prompt_payload = {
            "company_name": intel.get("company_name"),
            "company_domain": intel.get("company_domain"),
            "inferred_domain": intel.get("inferred_domain"),
            "trusted_inference": is_trusted,
            "linkedin_profile": bool(intel.get("linkedin_profile")),
            "hr_contact_count": len(intel.get("hr_contacts", [])),
            "press_mentions": intel.get("press_mentions"),
            "team_links": intel.get("team_links"),
            "recent_filings": intel.get("recent_filings"),
            "legitimacy_score": intel.get("legitimacy_score"),
        }
        prompt = (
            "Provide a concise assessment of the employer's legitimacy based on these open-source signals. "
            "Return JSON with keys: summary (string), alerts (array of short strings), "
            "confidence (0-100 integer). Do not fabricate facts.\n"
            f"Evidence: {json.dumps(prompt_payload, ensure_ascii=True)}"
        )
        result = structured_chat(
            prompt,
            system_prompt=(
                "You evaluate employer trustworthiness using public signals. "
                "Keep output factual and JSON-only."
            ),
            model="mistral-small-latest",
            max_tokens=250,
        )
        if result and isinstance(result, dict):
            return result
        logger.debug("LLM company assessment unavailable; falling back to heuristic scoring")
        return None
