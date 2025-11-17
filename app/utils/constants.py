"""Shared constant values for the job verifier application."""

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TOKEN_LIMIT = 200

TRUSTED_DOMAINS = {
    "amazon.jobs",
    "careers.google.com",
    "jobs.apple.com",
    "careers.microsoft.com",
    "jobs.netflix.com",
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "monster.com",
    "careerbuilder.com",
    "ziprecruiter.com",
    "oraclecloud.com",
    "oracle.com",
}

PAYWALL_INDICATORS = [
    "sign in",
    "log in",
    "login",
    "join now",
    "create account",
    "member login",
]

DUCKDUCKGO_HTML = "https://duckduckgo.com/html/"
PRESS_QUERY_TEMPLATE = "{company} press release"
EMPLOYEE_QUERY_TEMPLATE = '"{company}" ({keywords}) contact'

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

GENERIC_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "protonmail.com",
    "icloud.com",
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

SUSPICIOUS_TLDS = {"xyz", "top", "store", "site", "click", "info"}

EXTREME_SCAM_PHRASES = [
    "send money",
    "cash daily guaranteed",
    "pay upfront fee",
    "send gift card",
]

CRITICAL_FINANCIAL_FLAGS = [
    "send bitcoin",
    "wire money upfront",
    "purchase gift card",
]

FINANCIAL_RED_FLAGS = [
    "wire transfer",
    "gift card",
    "crypto",
    "bitcoin",
    "application fee",
    "training fee",
    "processing fee",
    "deposit",
]

SENSITIVE_INFO_FLAGS = [
    "ssn",
    "social security",
    "passport",
    "bank account",
    "routing number",
]

CATEGORY_WEIGHTS = {
    "acquisition": 0.1,
    "content": 0.8,
    "verification": 0.9,
    "financial": 1.4,
    "intelligence": 0.6,
}
