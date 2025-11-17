from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from app.utils import PAYWALL_INDICATORS, TOKEN_LIMIT, TRUSTED_DOMAINS, USER_AGENT

from .base import Agent, AgentError, JobContext


def _normalize_linkedin_url(url: str) -> str:
    """Extract clean LinkedIn job ID and convert to direct view URL."""
    # Extract job ID from various LinkedIn URL formats
    parsed = urlparse(url)

    # Check query parameters for currentJobId
    if "currentJobId=" in url:
        params = parse_qs(parsed.query)
        job_id = params.get("currentJobId", [None])[0]
        if job_id:
            return f"https://www.linkedin.com/jobs/view/{job_id}"

    # Check if already in /jobs/view/ format
    if "/jobs/view/" in url:
        job_id_match = re.search(r"/jobs/view/(\d+)", url)
        if job_id_match:
            return f"https://www.linkedin.com/jobs/view/{job_id_match.group(1)}"

    return url


def _detect_paywall(soup: BeautifulSoup, text: str) -> bool:
    """Detect if page requires login/authentication."""
    text_lower = text.lower()

    # Check for common paywall indicators in text
    if any(indicator in text_lower for indicator in PAYWALL_INDICATORS):
        # Verify it's not just mentioned in content
        if len(text.split()) < 100:  # Very short content suggests paywall
            return True

    # Check for login forms
    login_forms = soup.find_all("form", {"class": re.compile(r"login|sign-in", re.I)})
    if login_forms:
        return True

    return False


def _fetch_with_playwright(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch page content using Playwright for JavaScript-heavy sites."""
    if not PLAYWRIGHT_AVAILABLE:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)

            # Wait for content to load
            page.wait_for_timeout(2000)

            content = page.content()
            browser.close()
            return content
    except Exception:
        return None


def _fetch_with_selenium(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch page content using Selenium for JavaScript-heavy sites."""
    if not SELENIUM_AVAILABLE:
        return None

    try:
        options = ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(f"user-agent={USER_AGENT}")

        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(timeout)
        driver.get(url)

        # Wait for body to be present
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Additional wait for dynamic content
        driver.implicitly_wait(2)

        content = driver.page_source
        driver.quit()
        return content
    except Exception:
        return None


def _extract_title(soup: BeautifulSoup, domain: str) -> Optional[str]:
    """Extract job title with platform-specific selectors."""
    # LinkedIn-specific
    if "linkedin.com" in domain:
        title = soup.select_one(".top-card-layout__title, .topcard__title, h1.t-24")
        if title:
            return title.get_text(strip=True)

    # Indeed-specific
    if "indeed.com" in domain:
        title = soup.select_one("h1.jobsearch-JobInfoHeader-title, .icl-u-xs-mb--xs")
        if title:
            return title.get_text(strip=True)

    # Generic fallback
    title = soup.find("h1")
    if title:
        return title.get_text(strip=True)
    meta_title = soup.find("meta", {"property": "og:title"})
    if meta_title and meta_title.get("content"):
        return meta_title["content"].strip()
    return None


def _extract_company(soup: BeautifulSoup, domain: str) -> Optional[str]:
    """Extract company name with platform-specific selectors."""
    # LinkedIn-specific
    if "linkedin.com" in domain:
        company = soup.select_one(
            ".topcard__org-name-link, .topcard__flavor--black-link, "
            ".job-details-jobs-unified-top-card__company-name a"
        )
        if company:
            return company.get_text(strip=True)

    # Indeed-specific
    if "indeed.com" in domain:
        company = soup.select_one("[data-company-name], .icl-u-lg-mr--sm")
        if company:
            return company.get_text(strip=True)

    # Generic fallback
    company = soup.select_one(".topcard__org-name-link, .company-name, [data-company]")
    if company:
        return company.get_text(strip=True)
    meta_company = soup.find("meta", {"property": "og:site_name"})
    if meta_company and meta_company.get("content"):
        return meta_company["content"].strip()
    return None


def _extract_description(soup: BeautifulSoup, domain: str) -> Optional[str]:
    """Extract job description with platform-specific selectors."""
    # Amazon Jobs specific
    if "amazon.jobs" in domain:
        selectors = [
            ".job-detail-description",
            "#job-detail-body",
            "[data-test='description']",
            "div[class*='description']",
        ]
        for selector in selectors:
            container = soup.select_one(selector)
            if container:
                return container.get_text(" ", strip=True)

    # LinkedIn-specific
    if "linkedin.com" in domain:
        # Try multiple selectors for LinkedIn's changing structure
        selectors = [
            ".show-more-less-html__markup",
            ".description__text",
            ".job-view-layout .description",
            "div[class*='description']",
        ]
        for selector in selectors:
            container = soup.select_one(selector)
            if container:
                return container.get_text(" ", strip=True)

    # Indeed-specific
    if "indeed.com" in domain:
        container = soup.select_one("#jobDescriptionText, .jobsearch-jobDescriptionText")
        if container:
            return container.get_text(" ", strip=True)

    # Generic fallback
    container = soup.select_one(
        ".description, .job-description, [data-job-description], article, main"
    )
    if container:
        return container.get_text(" ", strip=True)
    body = soup.find("body")
    if body:
        text = body.get_text(" ", strip=True)
        return text if text else None
    return None


class DataAcquisitionAgent(Agent):
    """Fetches the job posting HTML and performs lightweight preprocessing."""

    name = "data_acquisition"

    def __init__(self, timeout: int = 10, use_browser: bool = True) -> None:
        self.timeout = timeout
        self.use_browser = use_browser  # Enable browser fallback for JS sites

    def run(self, context: JobContext) -> JobContext:
        # Normalize LinkedIn URLs to direct job view format
        original_url = context.url
        if "linkedin.com" in context.url.lower():
            context.url = _normalize_linkedin_url(context.url)

        domain = urlparse(context.url).netloc.lower()
        is_trusted = any(trusted in domain for trusted in TRUSTED_DOMAINS)

        # Step 1: Try standard requests + BeautifulSoup
        headers = {"User-Agent": USER_AGENT}
        html_content = None
        scraping_method = "requests"

        try:
            response = requests.get(context.url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            html_content = response.text
        except Exception as exc:
            raise AgentError(f"Failed to fetch URL: {exc}") from exc

        soup = BeautifulSoup(html_content, "html.parser")

        # Extract data with platform-specific selectors
        context.title = _extract_title(soup, domain) or "Title not found"
        context.company = _extract_company(soup, domain) or "Company not found"
        context.description = _extract_description(soup, domain) or "Description not found"

        # Step 2: If description is too short and browser support enabled, try JS rendering
        desc_length = len(context.description) if context.description != "Description not found" else 0

        if desc_length < 100 and self.use_browser and is_trusted:
            # Try Playwright first (faster, more reliable)
            if PLAYWRIGHT_AVAILABLE:
                playwright_html = _fetch_with_playwright(context.url, self.timeout)
                if playwright_html:
                    soup_pw = BeautifulSoup(playwright_html, "html.parser")
                    desc_pw = _extract_description(soup_pw, domain)
                    if desc_pw and len(desc_pw) > desc_length:
                        context.description = desc_pw
                        context.title = _extract_title(soup_pw, domain) or context.title
                        context.company = _extract_company(soup_pw, domain) or context.company
                        soup = soup_pw
                        scraping_method = "playwright"
                        desc_length = len(desc_pw)

            # Fallback to Selenium if Playwright didn't work
            if desc_length < 100 and SELENIUM_AVAILABLE:
                selenium_html = _fetch_with_selenium(context.url, self.timeout)
                if selenium_html:
                    soup_sel = BeautifulSoup(selenium_html, "html.parser")
                    desc_sel = _extract_description(soup_sel, domain)
                    if desc_sel and len(desc_sel) > desc_length:
                        context.description = desc_sel
                        context.title = _extract_title(soup_sel, domain) or context.title
                        context.company = _extract_company(soup_sel, domain) or context.company
                        soup = soup_sel
                        scraping_method = "selenium"
                        desc_length = len(desc_sel)

        context.raw_html = str(soup)
        context.meta["scraping_method"] = scraping_method
        context.meta["rendered_html_method"] = scraping_method
        context.meta["rendered_html"] = context.raw_html

        scraping_details = context.meta.setdefault("insights", {}).setdefault("scraping", {})
        scraping_details.update(
            {
                "method": scraping_method,
                "description_length": desc_length,
                "last_updated": datetime.utcnow().isoformat(),
            }
        )
        incomplete_reason = None

        # Detect paywall/login requirement
        full_text = f"{context.title} {context.description}"
        if _detect_paywall(soup, full_text):
            context.add_flag("acquisition", "Page requires login or authentication")
            raise AgentError(
                f"Cannot access job posting - login required. "
                f"Detected signs of authentication wall. "
                f"For LinkedIn jobs, you may need to be logged in. "
                f"Try: 1) Log into LinkedIn in browser, 2) Use Indeed/Glassdoor, "
                f"3) Visit company career page directly. "
                f"Original URL: {original_url}"
            )

        # Validate minimum content quality
        desc_length = len(context.description) if context.description != "Description not found" else 0
        domain = urlparse(context.url).netloc.lower()
        is_trusted = any(trusted in domain for trusted in TRUSTED_DOMAINS)

        if is_trusted:
            context.meta["trusted_domain"] = True

        if desc_length < 100:
            if is_trusted:
                # For trusted sites, this is likely a scraping issue, not a scam
                if scraping_method == "requests":
                    browsers_available = []
                    if PLAYWRIGHT_AVAILABLE:
                        browsers_available.append("Playwright")
                    if SELENIUM_AVAILABLE:
                        browsers_available.append("Selenium")

                    if browsers_available and not self.use_browser:
                        context.add_flag(
                            "acquisition",
                            "Unable to extract full description - site uses JavaScript. Browser support available but disabled.",
                        )
                        incomplete_reason = "Browser automation disabled; page likely requires JavaScript to render."
                    elif not browsers_available:
                        context.add_flag(
                            "acquisition",
                            "Unable to extract full description - install selenium/playwright for JS rendering support.",
                        )
                        incomplete_reason = "Install Playwright or Selenium to render the full job posting."
                    else:
                        context.add_flag(
                            "acquisition",
                            f"Unable to extract full description even with {scraping_method}. Visit URL directly.",
                        )
                        incomplete_reason = "JavaScript rendering attempted but content remained truncated."
                else:
                    context.add_flag(
                        "acquisition",
                        f"Description still short after {scraping_method} rendering ({desc_length} chars)",
                    )
                    incomplete_reason = f"Content remained short after {scraping_method} rendering."

                context.meta["scraping_incomplete"] = True
                context.meta["trusted_domain"] = True
            else:
                # For unknown sites, short content is more suspicious
                context.add_flag(
                    "acquisition",
                    f"Job description very short ({desc_length} chars) - may be incomplete or behind paywall",
                )
                incomplete_reason = "Non-trusted domain with very short content; manual review required."
            scraping_details.update(
                {
                    "status": "incomplete",
                    "reason": incomplete_reason,
                }
            )
            if incomplete_reason:
                context.meta["scraping_incomplete_reason"] = incomplete_reason
        else:
            # Successfully got content
            if scraping_method != "requests":
                context.meta["js_rendering_used"] = True
            scraping_details.update(
                {
                    "status": "complete",
                    "reason": "Description length sufficient for analysis.",
                }
            )

        context.trimmed_description = self._trim_description(context.description)
        context.meta.update(
            {
                "scraped_at": datetime.utcnow().isoformat(),
                "source_domain": urlparse(context.url).netloc,
                "token_count": len(context.trimmed_description.split())
                if context.trimmed_description
                else 0,
            }
        )

        context.contact_emails = self._extract_emails(context.description)
        context.contact_channels = self._extract_channels(context.description)
        context.salary_mentions = self._extract_salaries(context.description)

        if context.title == "Title not found":
            context.add_flag("acquisition", "Job title missing from page")
        if context.description == "Description not found":
            if is_trusted:
                context.add_flag("acquisition", "Unable to extract description from trusted site - may require JavaScript")
            else:
                context.add_flag("acquisition", "Job description missing from page")

        # Flag if critical data is missing (but softer for trusted domains)
        if not context.contact_emails:
            if is_trusted:
                # Major platforms rarely show emails publicly
                context.meta["no_email_expected"] = True
            else:
                context.add_flag("acquisition", "No contact email found - verification limited")

        if not context.salary_mentions:
            if is_trusted:
                # Many legitimate jobs don't list salary
                context.meta["no_salary_expected"] = True
            else:
                context.add_flag("acquisition", "No salary information found - financial analysis limited")

        return context

    @staticmethod
    def _trim_description(description: Optional[str]) -> str:
        if not description:
            return ""
        tokens = description.split()
        return " ".join(tokens[:TOKEN_LIMIT])

    @staticmethod
    def _extract_emails(text: Optional[str]) -> list[str]:
        if not text:
            return []
        pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        return list({match.lower() for match in re.findall(pattern, text)})

    @staticmethod
    def _extract_channels(text: Optional[str]) -> list[str]:
        if not text:
            return []
        channels = ["telegram", "whatsapp", "signal", "facebook", "instagram"]
        text_lower = text.lower()
        return [ch for ch in channels if ch in text_lower]

    @staticmethod
    def _extract_salaries(text: Optional[str]) -> list[str]:
        if not text:
            return []
        # Enhanced pattern to catch more salary formats
        patterns = [
            r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s?(?:per|/|-)?\s?(?:hour|hr|week|month|year|annum|annually)?",
            r"(?:£|€)\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s?(?:per|/|-)?\s?(?:hour|hr|week|month|year|annum|annually)?",
            r"\d{1,3}(?:,\d{3})+\s?(?:to|-)\s?\d{1,3}(?:,\d{3})+",
            r"(?:salary|pay|compensation):\s?\$?\d{1,3}(?:,\d{3})*",
        ]
        salaries = []
        for pattern in patterns:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            salaries.extend(matches)
        return list({match.strip() for match in salaries})
