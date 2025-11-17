"""Streamlit frontend for job posting verification — modern, minimalistic design."""

import html
from datetime import datetime

import streamlit as st
from concurrent.futures import ThreadPoolExecutor
import time
from app.utils.logger import configure_logging, get_logger
from app.workflows import ParentOrchestrator

# Configure logging
configure_logging()
logger = get_logger(__name__)

# ============================================================================
# Page Configuration
# ============================================================================
st.set_page_config(
    page_title="Job Posting Verifier",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# Modern CSS Styling
# ============================================================================
st.markdown(
    """
    <style>
    /* Global reset and foundation */
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }

    html, body, [data-testid="stAppViewContainer"] {
        background-color: #fafbfc;
        color: #0f1419;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
        line-height: 1.6;
    }

    /* Card layout with modern shadow */
    .card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04);
        border: 1px solid #e8ecf1;
        transition: box-shadow 0.2s ease;
    }
    .card:hover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    /* Verdict banners with WCAG AAA contrast */
    .verdict-fake {
        background: #fee2e2;
        border-left: 5px solid #dc2626;
        color: #7f1d1d;
        padding: 14px 16px;
        border-radius: 6px;
    }
    .verdict-suspicious {
        background: #fed7aa;
        border-left: 5px solid #ea580c;
        color: #7c2d12;
        padding: 14px 16px;
        border-radius: 6px;
    }
    .verdict-legit {
        background: #dcfce7;
        border-left: 5px solid #16a34a;
        color: #15803d;
        padding: 14px 16px;
        border-radius: 6px;
    }
    .verdict-incomplete {
        background: #f3f4f6;
        border-left: 5px solid #6b7280;
        color: #374151;
        padding: 14px 16px;
        border-radius: 6px;
    }
    .verdict-error {
        background: #fee2e2;
        border-left: 5px solid #991b1b;
        color: #7f1d1d;
        padding: 14px 16px;
        border-radius: 6px;
    }

    /* Risk score badges */
    .risk-high {
        color: #dc2626;
        font-weight: 700;
    }
    .risk-medium {
        color: #ea580c;
        font-weight: 700;
    }
    .risk-low {
        color: #16a34a;
        font-weight: 700;
    }

    /* Section headers */
    .section-header {
        font-size: 16px;
        font-weight: 600;
        color: #0f1419;
        margin-top: 24px;
        margin-bottom: 12px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        opacity: 0.85;
    }

    /* Streamlit metric cards */
    [data-testid="metric-container"] {
        background-color: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px;
    }

    /* Expanders */
    [data-testid="stExpander"] {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        background-color: #ffffff;
    }
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        padding-bottom: 12px;
    }

    /* Dividers */
    hr {
        border: none;
        border-top: 1px solid #e5e7eb;
        margin: 20px 0;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #f9fafb;
        color: #0f1419;
        border-right: 1px solid #e5e7eb;
    }

    /* Buttons with better contrast */
    [data-testid="stButton"] button {
        background-color: #0f1419 !important;
        color: #ffffff !important;
        border: none;
        border-radius: 6px;
        font-weight: 600;
        transition: background-color 0.2s ease;
    }
    [data-testid="stButton"] button:hover {
        background-color: #1f2937 !important;
    }

    /* Text inputs */
    [data-testid="stTextInput"] input {
        border: 1px solid #d1d5db !important;
        border-radius: 6px !important;
        padding: 10px 12px !important;
        font-size: 14px !important;
    }

    /* Footer */
    .footer {
        text-align: center;
        color: #6b7280;
        font-size: 12px;
        margin-top: 40px;
        padding-top: 24px;
        border-top: 1px solid #e5e7eb;
    }

    /* Headings hierarchy */
    h1 {
        color: #0f1419;
        font-weight: 700;
        font-size: 28px;
        margin-bottom: 8px;
    }
    h2 {
        color: #111827;
        font-weight: 700;
        font-size: 22px;
        margin-top: 20px;
        margin-bottom: 12px;
    }
    h3, h4 {
        color: #1f2937;
        font-weight: 600;
    }
    p, li, span {
        color: #374151;
    }

    /* Structured profile layout */
    .profile-grid {
        display: grid;
        gap: 12px 16px;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        margin-top: 16px;
    }
    .profile-item {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }
    .profile-label {
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.4px;
        color: #6b7280;
    }
    .profile-value {
        font-size: 15px;
        color: #0f1419;
    }
    .skill-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 18px;
    }
    .skill-tag {
        background-color: #eef2ff;
        border: 1px solid #c7d2fe;
        border-radius: 999px;
        color: #3730a3;
        font-size: 13px;
        padding: 4px 12px;
        font-weight: 500;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================================
# Session State Initialization
# ============================================================================
if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = ParentOrchestrator()

if "results_history" not in st.session_state:
    st.session_state.results_history = []

# ============================================================================
# Utility Functions
# ============================================================================


def get_verdict_emoji(verdict: str) -> str:
    """Return emoji for verdict."""
    return {
        "fake": "🚨",
        "suspicious": "⚠️",
        "legit": "✅",
        "incomplete_data": "ℹ️",
        "error": "❌",
    }.get(verdict, "❓")


def get_verdict_style(verdict: str) -> str:
    """Return CSS class for verdict."""
    return {
        "fake": "verdict-fake",
        "suspicious": "verdict-suspicious",
        "legit": "verdict-legit",
        "incomplete_data": "verdict-incomplete",
        "error": "verdict-error",
    }.get(verdict, "verdict-incomplete")


def get_risk_color(score: int) -> str:
    """Return risk color class."""
    if score >= 70:
        return "risk-high"
    elif score >= 40:
        return "risk-medium"
    return "risk-low"


# ============================================================================
# Display Components
# ============================================================================


def render_verdict_banner(verdict: str, recommendation: str, risk_score: int | None) -> None:
    """Render verdict banner with recommendation."""
    emoji = get_verdict_emoji(verdict)
    style = get_verdict_style(verdict)
    title = verdict.replace("_", " ").title()
    
    st.markdown(
        f"""
        <div class="card {style}">
            <h2 style="margin-bottom: 12px;">{emoji} {title}</h2>
            <p style="font-size: 15px; line-height: 1.6; color: #212529;">
                {recommendation}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_key_metrics(risk_score: int | None, confidence: int | None, scraping_method: str) -> None:
    """Render key metrics in a clean layout."""
    col1, col2, col3 = st.columns(3, gap="medium")
    
    with col1:
        if isinstance(risk_score, (int, float)):
            color_class = get_risk_color(int(risk_score))
            st.markdown(
                f'<p class="{color_class}" style="font-size: 28px; margin: 0;">Risk: {int(risk_score)}/100</p>',
                unsafe_allow_html=True,
            )
            st.caption("Risk Assessment Score")
        else:
            st.markdown('<p style="color: #6c757d; font-size: 14px;">Risk: N/A</p>', unsafe_allow_html=True)
    
    with col2:
        confidence_val = f"{confidence}%" if confidence is not None else "N/A"
        st.metric("Confidence", confidence_val, help="Confidence in the verdict")
    
    with col3:
        st.metric("Source", scraping_method or "N/A", help="Data acquisition method")


def render_source_info(source: dict, summary: dict) -> None:
    """Render source information in a card."""
    st.markdown('<p class="section-header">📋 Source Information</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2, gap="medium")
    with col1:
        st.markdown(f"**Title:** {source.get('title', 'N/A')}")
        st.markdown(f"**Company:** {source.get('company', 'N/A')}")
    with col2:
        st.markdown(f"**URL:** {source.get('url', 'N/A')}")
        st.markdown(f"**Domain:** {summary.get('source_domain', 'N/A')}")


def render_structured_profile(profile: dict) -> None:
    """Render LLM-extracted structured profile in a friendly format."""
    if not isinstance(profile, dict):
        return

    def safe_text(value: object) -> str:
        if value is None:
            return "N/A"
        value_str = str(value).strip()
        return html.escape(value_str) if value_str else "N/A"

    url_value = profile.get("url")
    url_display = (
        f'<a href="{html.escape(url_value)}" target="_blank" rel="noopener noreferrer">{html.escape(url_value)}</a>'
        if isinstance(url_value, str) and url_value.strip()
        else "N/A"
    )

    authenticity = profile.get("authenticity_score")
    if isinstance(authenticity, (int, float)):
        clamped = max(min(float(authenticity), 1.0), 0.0)
        authenticity_display = f"{clamped * 100:.0f}%"
    elif authenticity not in (None, ""):
        authenticity_display = str(authenticity).strip()
    else:
        authenticity_display = "N/A"
    authenticity_display = html.escape(authenticity_display)

    scraped_at = profile.get("scraped_at")
    if isinstance(scraped_at, str) and scraped_at.strip():
        human = scraped_at.replace("T", " ")[:19]
        scraped_display = html.escape(human)
    else:
        scraped_display = "N/A"

    fields = [
        ("Job Title", safe_text(profile.get("job_title"))),
        ("Company", safe_text(profile.get("company"))),
        ("Team", safe_text(profile.get("team"))),
        ("Location", safe_text(profile.get("location"))),
        ("Experience Required", safe_text(profile.get("experience_required"))),
        ("Education Required", safe_text(profile.get("education_required"))),
        ("Job Type", safe_text(profile.get("job_type"))),
        ("Authenticity Score", authenticity_display),
        ("Verified Domain", safe_text(profile.get("verified_domain"))),
        ("Posting URL", url_display),
        ("Scraped At", scraped_display),
    ]

    grid_html = "".join(
        (
            '<div class="profile-item">'
            f'<span class="profile-label">{label}</span>'
            f'<span class="profile-value">{value}</span>'
            '</div>'
        )
        for label, value in fields
    )

    skills = [skill for skill in profile.get("skills", []) if isinstance(skill, str) and skill.strip()]
    skill_tags = "".join(
        f'<span class="skill-tag">{html.escape(skill.strip())}</span>' for skill in skills
    )
    skills_block = (
        f'<div class="skill-tags">{skill_tags}</div>'
        if skill_tags
        else '<p style="margin-top:16px; color:#6b7280;">No standout skills extracted.</p>'
    )

    st.markdown('<p class="section-header">🧭 Structured Job Profile</p>', unsafe_allow_html=True)
    card_html = (
        '<div class="card">'
        f'<div class="profile-grid">{grid_html}</div>'
        f'{skills_block}'
        '</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)


def render_flags(flags: dict) -> None:
    """Render detected flags in organized categories."""
    flag_count = sum(len(f) for f in flags.values())
    
    if flag_count == 0:
        st.success("✨ No red flags detected!")
        return
    
    st.markdown(f'<p class="section-header">🚩 Detected Flags ({flag_count} total)</p>', unsafe_allow_html=True)
    
    categories = {
        "acquisition": "📥 Data Acquisition",
        "content": "📝 Content Analysis",
        "verification": "✔️ Source Verification",
        "financial": "💰 Financial Risk",
        "intelligence": "🔍 Company Intelligence",
    }
    
    for category_key, category_name in categories.items():
        flag_list = flags.get(category_key, [])
        if flag_list:
            with st.expander(f"{category_name} ({len(flag_list)})"):
                for i, flag in enumerate(flag_list, 1):
                    st.markdown(f"**{i}.** {flag}")


def render_company_intel(intel: dict) -> None:
    """Render company intelligence findings."""
    st.markdown('<p class="section-header">🏢 Company Intelligence</p>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3, gap="medium")
    with col1:
        st.metric("Domain", intel.get("company_domain") or "N/A")
    with col2:
        st.metric("Legitimacy", f"{intel.get('legitimacy_score', 0)}/100")
    with col3:
        trusted = "✅ Yes" if intel.get("trusted_inference") else "❌ No"
        st.metric("Trusted", trusted)
    
    st.divider()
    
    # Web presence overview
    web_sources = intel.get("web_presence") or []
    if web_sources:
        with st.expander("🌐 Web Presence", expanded=False):
            for source in web_sources:
                title = source.get("title") or source.get("url") or "Source"
                url = source.get("url")
                tag = source.get("tag", "external").title()
                snippet = source.get("snippet")
                if url:
                    st.markdown(f"**[{title}]({url})** — {tag}")
                else:
                    st.markdown(f"**{title}** — {tag}")
                if snippet:
                    st.caption(snippet)
    else:
        status = intel.get("web_presence_status", "not_found").replace("_", " ").title()
        st.info(f"Web Presence: {status}")
    
    # HR Contacts
    if intel.get("hr_contacts"):
        with st.expander(f"👥 HR Contacts ({len(intel['hr_contacts'])})", expanded=False):
            for contact in intel["hr_contacts"]:
                name = contact.get("name") or "Contact"
                role = contact.get("role")
                profile = contact.get("profile")
                line = f"**{name}**"
                if role:
                    line += f" — {role}"
                if profile:
                    line += f"  \n[{profile}]({profile})"
                st.markdown(line)
    else:
        status = intel.get("hr_contacts_status", "not_visible").replace("_", " ").title()
        st.info(f"HR Contacts: {status}")
    
    # Additional Signals
    col1, col2, col3 = st.columns(3, gap="medium")
    with col1:
        press = len(intel.get("press_mentions", []))
        st.metric("Press Mentions", press)
    with col2:
        team = len(intel.get("team_links", []))
        st.metric("Team Links", team)
    with col3:
        filings = "✅" if intel.get("recent_filings") else "❌"
        st.metric("SEC Filings", filings)


def render_detailed_analysis(summary: dict, scraping_incomplete: bool) -> None:
    """Render detailed analysis summary."""
    with st.expander("📊 Detailed Analysis", expanded=False):
        col1, col2 = st.columns(2, gap="medium")
        
        with col1:
            st.metric(
                "Content Score",
                summary.get("content_score", "N/A"),
                help="Analysis of content quality and red flags" if not scraping_incomplete else "Not evaluated",
            )
            st.metric("Verification Score", summary.get("verification_score", "N/A"))
        
        with col2:
            st.metric("Financial Score", summary.get("financial_score", "N/A"))
            scraped_at = summary.get("scraped_at", "N/A")
            if scraped_at != "N/A":
                st.metric("Scraped At", scraped_at[:19])
        
        if summary.get("flag_summary"):
            st.markdown("**Flag Summary:**")
            st.json(summary["flag_summary"])


def render_result(result: dict) -> None:
    """Render complete verification result."""
    verdict = result.get("verdict", "error")
    risk_score = result.get("risk_score")
    confidence = result.get("confidence")
    summary = result.get("summary", {})
    source = result.get("source", {})
    
    # Verdict banner
    render_verdict_banner(verdict, result.get("recommendation", ""), risk_score)
    
    st.divider()
    
    # Key metrics
    render_key_metrics(risk_score, confidence, summary.get("scraping_method", "N/A"))
    
    st.divider()
    
    # Scraping status warning
    scraping_info = summary.get("insights", {}).get("scraping", {})
    scraping_incomplete = scraping_info.get("status") == "incomplete" or summary.get("scraping_incomplete")
    
    if scraping_incomplete:
        reason = (
            scraping_info.get("reason")
            or summary.get("scraping_incomplete_reason")
            or "Description could not be fully captured."
        )
        st.warning(f"⚠️ Incomplete Scrape: {reason}")
    
    # Source information
    render_source_info(source, summary)
    
    st.divider()
    
    profile = summary.get("structured_profile")
    if isinstance(profile, dict):
        render_structured_profile(profile)
        st.divider()

    # Flags
    render_flags(result.get("flags", {}))
    
    st.divider()
    
    # Company intelligence
    if summary.get("company_intel"):
        render_company_intel(summary["company_intel"])
        st.divider()
    
    # Detailed analysis
    render_detailed_analysis(summary, scraping_incomplete)


def render_history_item(item: dict, index: int) -> None:
    """Render a single history item."""
    verdict = item.get("verdict", "unknown")
    emoji = get_verdict_emoji(verdict)
    risk_score = item.get("risk_score")
    timestamp = item.get("timestamp", "")
    url = item.get("url", "N/A")
    
    with st.expander(f"{emoji} {verdict.title()} — {risk_score or 'N/A'}/100 ({timestamp})"):
        st.markdown(f"**URL:** {url}")
        col1, col2 = st.columns(2, gap="small")
        with col1:
            if st.button("🔄 Re-analyze", key=f"reanalyze_{index}"):
                st.session_state.url_input = url
                st.rerun()
        with col2:
            if st.button("🗑️ Remove", key=f"remove_{index}"):
                st.session_state.results_history.pop(index)
                st.rerun()


# ============================================================================
# Main Application
# ============================================================================


def main():
    """Main Streamlit application."""
    # Header
    st.title("🔍 Job Posting Verifier")
    st.markdown(
        "Analyze job postings for fraud, scams, and legitimacy signals using AI-powered verification."
    )
    st.divider()
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        st.markdown(
            """
            This tool uses:
            - **Web scraping** to extract job content
            - **Content analysis** to detect scam patterns
            - **Source verification** for domain legitimacy
            - **Financial risk** assessment
            - **Company intelligence** gathering
            """
        )
        
        if st.session_state.results_history:
            if st.button("📜 Clear History", use_container_width=True):
                st.session_state.results_history = []
                st.rerun()
    
    # Main input area
    st.markdown('<p class="section-header">Enter Job Posting URL</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([4, 1], gap="small")
    with col1:
        url_input = st.text_input(
            "URL",
            placeholder="https://linkedin.com/jobs/view/123456789",
            key="url_input",
            label_visibility="collapsed",
        )
    with col2:
        analyze_btn = st.button("🔍 Analyze", use_container_width=True, type="primary")
    
    st.divider()
    
    # Analysis execution
    if analyze_btn and url_input.strip():
        progress_placeholder = st.empty()
        progress_bar = progress_placeholder.progress(0, text="🚀 Starting analysis...")
        progress_steps = [
            (20, "🌐 Scraping job posting..."),
            (55, "🧠 Analyzing content and signals..."),
            (80, "🏢 Verifying company information..."),
            (95, "🧾 Synthesizing risk assessment..."),
        ]

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    st.session_state.orchestrator.process_job, url_input.strip()
                )
                last_value = 0
                for pct, message in progress_steps:
                    if future.done():
                        break
                    progress_bar.progress(pct, text=message)
                    last_value = pct
                    time.sleep(0.6)
                while not future.done():
                    last_value = min(last_value + 3, 97)
                    progress_bar.progress(last_value, text="📊 Finalizing report...")
                    time.sleep(0.4)
                result = future.result()

            progress_bar.progress(100, text="✅ Analysis complete")
            time.sleep(0.4)
            progress_placeholder.empty()
            # Add to history
            st.session_state.results_history.insert(
                0,
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "url": url_input.strip(),
                    "verdict": result.get("verdict", "error"),
                    "risk_score": result.get("risk_score"),
                },
            )
            
            # Render result
            render_result(result)

        except Exception as exc:
            progress_bar.progress(100, text="❌ Analysis failed")
            time.sleep(0.5)
            progress_placeholder.empty()
            st.error(f"❌ Analysis failed: {str(exc)}")
            logger.exception("Analysis error")
    
    elif analyze_btn:
        st.warning("⚠️ Please enter a URL to analyze.")
    
    # Recent analyses sidebar
    if st.session_state.results_history:
        st.divider()
        st.markdown('<p class="section-header">📚 Recent Analyses</p>', unsafe_allow_html=True)
        
        for i, item in enumerate(st.session_state.results_history[:10]):
            render_history_item(item, i)
    
    # Footer
    st.markdown(
        """
        <div class="footer">
            <p>🛡️ Job Posting Verifier | Multi-Agent Fraud Detection System</p>
            <p style="margin-top: 8px; font-size: 11px;">Developed with ❤️ for job seekers</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
