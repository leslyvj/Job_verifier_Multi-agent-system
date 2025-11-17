from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

from app.config.settings import get_settings
from app.services.llm import llm_available, structured_chat
from app.utils.constants import (
	DUCKDUCKGO_HTML,
	GENERIC_EMAIL_DOMAINS,
	JOB_BOARD_DOMAINS,
	PRESS_QUERY_TEMPLATE,
	TRUSTED_BRAND_KEYWORDS,
	TRUSTED_DOMAINS,
	TRUSTED_ENTERPRISE_SUFFIXES,
	USER_AGENT,
)
from app.utils.logger import get_logger

from .base import Agent, JobContext

try:  # Playwright is optional
	from playwright.sync_api import sync_playwright  # type: ignore[import]

	PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover - environment without playwright
	PLAYWRIGHT_AVAILABLE = False

logger = get_logger(__name__)

TAVILY_ENDPOINT = "https://api.tavily.com/search"
SCAM_KEYWORDS = ("scam", "fraud", "complaint", "lawsuit", "ripoff", "warning")
REVIEW_DOMAINS = {
	"glassdoor.com",
	"indeed.com",
	"comparably.com",
	"ambitionbox.com",
	"trustpilot.com",
}


class CompanyIntelligenceAgent(Agent):
	"""Collects open-source employer intelligence using Tavily (if configured)."""

	name = "company_intelligence"

	def __init__(self, request_timeout: int = 10) -> None:
		self.request_timeout = request_timeout
		settings = get_settings()
		self.tavily_api_key = settings.tavily_api_key

	def run(self, context: JobContext) -> JobContext:
		company_name = (context.company or "").strip()
		source_domain = str(context.meta.get("source_domain") or "")
		job_role = str(context.meta.get("job_role") or context.title or "").strip()

		existing_intel = dict(context.meta.get("company_intel") or {})

		inferred_domain = existing_intel.get("inferred_domain") or self._infer_company_domain(context)
		normalised_domain = self._normalise_domain(
			existing_intel.get("company_domain") or inferred_domain or source_domain
		)

		intel: Dict[str, Any] = {
			**existing_intel,
			"company_name": company_name or existing_intel.get("company_name"),
			"source_domain": source_domain or existing_intel.get("source_domain"),
			"inferred_domain": inferred_domain,
			"company_domain": normalised_domain,
			"job_role": job_role or existing_intel.get("job_role"),
			"provider": "company_intelligence_agent",
			"tavily_provider": bool(self.tavily_api_key),
		}

		llm_ready = llm_available()

		is_trusted = bool(context.meta.get("trusted_domain"))
		domain_candidate = (normalised_domain or source_domain or "").lower()
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
			return context

		if not normalised_domain and not is_trusted:
			context.add_flag(
				"intelligence",
				"Unable to determine official company domain from posting",
			)

		press_results: List[Dict[str, str]] = []
		if company_name:
			press_query = PRESS_QUERY_TEMPLATE.format(company=company_name)
			press_results = self._search_web(press_query, max_results=6)
		intel["press_mentions"] = press_results

		team_probe = self._probe_official_pages(normalised_domain, company_name)
		if team_probe["team_links"]:
			intel["team_links"] = team_probe["team_links"]
		if not intel.get("press_mentions") and team_probe["press_mentions"]:
			intel["press_mentions"] = team_probe["press_mentions"]

		employee_reviews: List[Dict[str, str]] = []
		if company_name:
			review_candidates = self._search_web(f"{company_name} Glassdoor reviews", max_results=6)
			employee_reviews = self._filter_results(review_candidates, include_domains=REVIEW_DOMAINS)
		if employee_reviews:
			intel["employee_reviews"] = employee_reviews

		scam_results: List[Dict[str, str]] = []
		if company_name:
			scam_candidates = self._search_web(f"{company_name} scam warning", max_results=6)
			scam_results = [item for item in scam_candidates if self._looks_like_scam_report(item)]
		if scam_results:
			intel["scam_reports"] = scam_results
			context.add_flag(
				"intelligence",
				"Potential scam warnings detected via open web search",
			)

		web_presence = self._search_web(f"{company_name} company profile", max_results=6) if company_name else []
		if web_presence:
			intel["web_presence"] = web_presence
			intel["web_presence_status"] = "found"
		else:
			intel.setdefault("web_presence_status", "not_found")

		hr_contacts = self._discover_hr_contacts(company_name, normalised_domain, job_role)
		if llm_ready and hr_contacts:
			refined_contacts = self._refine_contacts_with_llm(company_name, normalised_domain, hr_contacts)
			if refined_contacts is not None:
				hr_contacts = refined_contacts
		intel["hr_contacts"] = hr_contacts
		if not hr_contacts:
			intel["hr_contacts_status"] = "not_visible" if is_trusted else "not_found"

		has_filings = self._has_recent_filings(company_name)
		intel["recent_filings"] = has_filings

		legitimacy_score = self._score_legitimacy(
			bool(normalised_domain),
			is_trusted,
			len(intel.get("web_presence") or []),
			len(hr_contacts),
			len(intel.get("press_mentions") or []),
			len(intel.get("team_links") or []),
			has_filings,
			bool(employee_reviews),
			bool(scam_results),
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

		return context

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
			"Filter the provided leads to genuine HR or recruiting touchpoints. "
			"Prefer emails hosted on the official company domain and remove spam or unrelated entries. "
			"Return JSON with a 'contacts' array containing name, role, profile.\n"
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
			if domain and domain.lower() not in profile.lower() and "@" not in name:
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

	def _search_web(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
		results = self._tavily_search(query, max_results)
		if results:
			return results
		return self._duckduckgo_results(query, max_results)

	def _tavily_search(self, query: str, max_results: int) -> List[Dict[str, str]]:
		if not self.tavily_api_key:
			return []
		payload = {
			"api_key": self.tavily_api_key,
			"query": query,
			"search_depth": "advanced",
			"max_results": max_results,
		}
		try:
			response = requests.post(TAVILY_ENDPOINT, json=payload, timeout=self.request_timeout)
			response.raise_for_status()
		except requests.RequestException as exc:  # pragma: no cover - network variability
			logger.debug("Tavily search failed for '%s': %s", query, exc)
			return []

		data = response.json()
		formatted: List[Dict[str, str]] = []
		for item in data.get("results", [])[:max_results]:
			url = item.get("url", "").strip()
			if not url:
				continue
			formatted.append(
				{
					"title": (item.get("title") or "").strip(),
					"url": url,
					"snippet": (item.get("content") or "").strip(),
				}
			)
		return formatted

	def _filter_results(
		self,
		results: List[Dict[str, str]],
		include_domains: Optional[set[str]] = None,
	) -> List[Dict[str, str]]:
		if not include_domains:
			return results
		filtered: List[Dict[str, str]] = []
		for item in results:
			url = (item.get("url") or "").lower()
			if any(domain in url for domain in include_domains):
				filtered.append(item)
		return filtered

	def _looks_like_scam_report(self, result: Dict[str, str]) -> bool:
		title = (result.get("title") or "").lower()
		snippet = (result.get("snippet") or "").lower()
		url = (result.get("url") or "").lower()
		return any(keyword in title or keyword in snippet or keyword in url for keyword in SCAM_KEYWORDS)

	def _discover_hr_contacts(
		self,
		company_name: str,
		domain: Optional[str],
		job_role: str,
	) -> List[Dict[str, str]]:
		if not company_name:
			return []

		domain_filter = domain or ""
		queries = [
			f'"{company_name}" "HR email"',
			f'"{company_name}" "recruiting contact"',
			f'"{company_name}" "talent acquisition" email',
		]
		if domain_filter:
			queries.append(f'site:{domain_filter} "contact" "hr"')
			queries.append(f'site:{domain_filter} "recruiting"')
		role_hint = job_role.split(",")[0].strip()
		if role_hint and 2 <= len(role_hint.split()) <= 5:
			queries.append(f'"{company_name}" "{role_hint}" contact')

		contacts: List[Dict[str, str]] = []
		seen_emails: set[str] = set()

		for query in queries:
			results = self._search_web(query, max_results=6)
			for result in results:
				url = (result.get("url") or "").strip()
				if not url or "linkedin.com" in url.lower():
					continue
				snippet = result.get("snippet") or ""
				emails = self._extract_emails(snippet)
				if not emails:
					page_html = self._safe_fetch(url)
					emails = self._extract_emails(page_html)
				for email in emails:
					if domain_filter and domain_filter not in email:
						continue
					if email in seen_emails:
						continue
					seen_emails.add(email)
					contacts.append(
						{
							"name": email,
							"role": (result.get("title") or "Contact").split("|")[0].strip(),
							"profile": url,
						}
					)
					if len(contacts) >= 5:
						return contacts
		return contacts

	def _probe_official_pages(
		self, domain: Optional[str], company_name: str
	) -> Dict[str, List[str]]:
		team_links: List[str] = []
		press_links: List[Dict[str, str]] = []

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

		if company_name and not press_links:
			press_query = PRESS_QUERY_TEMPLATE.format(company=company_name)
			press_links = self._duckduckgo_results(press_query, max_results=4)

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
		for email in context.contact_emails:
			if "@" not in email:
				continue
			domain = email.split("@")[-1].lower()
			if domain not in GENERIC_EMAIL_DOMAINS and "." in domain:
				return domain

		source_domain = context.meta.get("source_domain")
		if source_domain and not any(board in source_domain for board in JOB_BOARD_DOMAINS):
			return source_domain.lower()

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
	def _extract_emails(text: Optional[str]) -> List[str]:
		if not text:
			return []
		pattern = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
		return sorted({match.lower() for match in pattern.findall(text)})

	@staticmethod
	def _score_legitimacy(
		has_domain: bool,
		is_trusted: bool,
		web_presence_count: int,
		hr_contact_count: int,
		press_count: int,
		team_link_count: int,
		has_filings: bool,
		has_reviews: bool,
		has_scam_hits: bool,
	) -> int:
		score = 35 if is_trusted else 20
		if has_domain:
			score += 20
		score += min(15, web_presence_count * 3)
		if hr_contact_count:
			score += min(15, hr_contact_count * 3)
		if press_count:
			score += min(10, press_count * 2)
		if team_link_count:
			score += min(10, team_link_count * 3)
		if has_filings:
			score += 10
		if has_reviews:
			score += 5
		if has_scam_hits:
			score -= 25
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
			"web_presence_count": len(intel.get("web_presence", [])),
			"hr_contact_count": len(intel.get("hr_contacts", [])),
			"press_mentions": intel.get("press_mentions"),
			"team_links": intel.get("team_links"),
			"recent_filings": intel.get("recent_filings"),
			"legitimacy_score": intel.get("legitimacy_score"),
			"scam_reports": intel.get("scam_reports"),
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

