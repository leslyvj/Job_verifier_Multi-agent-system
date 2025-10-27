"""Streamlit frontend for job posting verification."""

import json
import logging
from datetime import datetime

import streamlit as st

from src.jobverifier.orchestrator import ParentOrchestrator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="Job Posting Verifier",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
    <style>
    .verdict-fake {
        background-color: #ffcccc;
        padding: 20px;
        border-radius: 5px;
        border-left: 4px solid #ff0000;
    }
    .verdict-suspicious {
        background-color: #fff3cd;
        padding: 20px;
        border-radius: 5px;
        border-left: 4px solid #ff9800;
    }
    .verdict-legit {
        background-color: #d4edda;
        padding: 20px;
        border-radius: 5px;
        border-left: 4px solid #28a745;
    }
    .verdict-incomplete {
        background-color: #e2e3e5;
        padding: 20px;
        border-radius: 5px;
        border-left: 4px solid #6c757d;
    }
    .risk-score-high {
        color: #ff0000;
        font-weight: bold;
    }
    .risk-score-medium {
        color: #ff9800;
        font-weight: bold;
    }
    .risk-score-low {
        color: #28a745;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Session state initialization
if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = ParentOrchestrator()

if "results_history" not in st.session_state:
    st.session_state.results_history = []


def get_verdict_emoji(verdict: str) -> str:
    """Return emoji for verdict."""
    verdicts = {
        "fake": "🚨",
        "suspicious": "⚠️",
        "legit": "✅",
        "incomplete_data": "ℹ️",
        "error": "❌",
    }
    return verdicts.get(verdict, "❓")


def get_verdict_style(verdict: str) -> str:
    """Return CSS class for verdict."""
    styles = {
        "fake": "verdict-fake",
        "suspicious": "verdict-suspicious",
        "legit": "verdict-legit",
        "incomplete_data": "verdict-incomplete",
        "error": "verdict-incomplete",
    }
    return styles.get(verdict, "")


def get_risk_score_color(score: int) -> str:
    """Return CSS class for risk score."""
    if score >= 70:
        return "risk-score-high"
    elif score >= 40:
        return "risk-score-medium"
    else:
        return "risk-score-low"


def render_metric(label: str, value, *, disabled: bool = False, placeholder: str = "Not available") -> None:
    """Render a metric, falling back to greyed-out text when disabled."""
    if disabled:
        st.markdown(
            f"<p style='color:#6c757d'><strong>{label}:</strong> {placeholder}</p>",
            unsafe_allow_html=True,
        )
    else:
        st.metric(label, value if value is not None else "N/A")


def display_flags(flags: dict) -> None:
    """Display all flags in organized categories."""
    st.subheader("🚩 Detected Flags")
    
    categories = {
        "acquisition": "Data Acquisition",
        "content": "Content Analysis",
        "verification": "Source Verification",
        "financial": "Financial Risk",
        "intelligence": "Company Intelligence",
    }
    
    has_flags = False
    for category_key, category_name in categories.items():
        flag_list = flags.get(category_key, [])
        if flag_list:
            has_flags = True
            with st.expander(f"**{category_name}** ({len(flag_list)})"):
                for i, flag in enumerate(flag_list, 1):
                    st.write(f"{i}. {flag}")
    
    if not has_flags:
        st.info("✨ No red flags detected!")


def display_company_intel(intel: dict) -> None:
    """Display company intelligence findings."""
    st.subheader("🏢 Company Intelligence")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Company Domain", intel.get("company_domain") or "N/A")
    with col2:
        st.metric(
            "Legitimacy Score",
            f"{intel.get('legitimacy_score', 0)}/100",
        )
    with col3:
        trusted = "✅ Yes" if intel.get("trusted_inference") else "❌ No"
        st.metric("Trusted Inference", trusted)
    
    # LinkedIn Profile
    if intel.get("linkedin_profile"):
        with st.expander("LinkedIn Profile"):
            profile = intel["linkedin_profile"]
            st.write(f"**URL:** {profile.get('url')}")
            st.write(f"**Followers:** {profile.get('followers') or 'N/A'}")
            st.write(f"**Industry:** {profile.get('industry') or 'N/A'}")
            st.write(f"**Employee Count:** {profile.get('employee_count') or 'N/A'}")
    else:
        status = intel.get("linkedin_profile_status", "unknown")
        st.info(f"LinkedIn profile: {status.replace('_', ' ').title()}")
    
    # HR Contacts
    if intel.get("hr_contacts"):
        with st.expander(f"HR/Recruiting Contacts ({len(intel['hr_contacts'])})"):
            for contact in intel["hr_contacts"]:
                st.write(f"👤 **{contact.get('name')}**")
                if contact.get("role"):
                    st.write(f"   Role: {contact['role']}")
                if contact.get("profile"):
                    st.write(f"   Profile: {contact['profile']}")
    else:
        status = intel.get("hr_contacts_status", "unknown")
        st.info(f"HR contacts: {status.replace('_', ' ').title()}")
    
    # Additional Signals
    col1, col2, col3 = st.columns(3)
    with col1:
        press_count = len(intel.get("press_mentions", []))
        st.metric("Press Mentions", press_count)
        if press_count == 0:
            st.caption("No recent press mentions surfaced in quick search.")
    with col2:
        team_links = len(intel.get("team_links", []))
        st.metric("Team Links Found", team_links)
        if team_links == 0:
            st.caption("Company team/careers pages not detected automatically.")
    with col3:
        filings = "✅ Yes" if intel.get("recent_filings") else "❌ No"
        st.metric("Recent SEC Filings", filings)


def display_result(result: dict) -> None:
    """Display verification result with formatting."""
    # Use .get to avoid KeyError when fields are missing
    verdict = result.get("verdict", "error")
    risk_score = result.get("risk_score")
    confidence = result.get("confidence")
    
    # Verdict banner
    emoji = get_verdict_emoji(verdict)
    style = get_verdict_style(verdict)
    verdict_title = verdict.replace("_", " ").title()
    
    st.markdown(
        f"""
        <div class="{style}">
            <h2>{emoji} {verdict_title}</h2>
            <p style="font-size: 16px;">{result.get('recommendation', '')}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        # Handle missing or non-numeric risk_score gracefully
        if isinstance(risk_score, (int, float)):
            risk_color = get_risk_score_color(int(risk_score))
            st.markdown(
                f'<p class="{risk_color}">Risk Score: {int(risk_score)}/100</p>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<p style="color:#6c757d">Risk Score: N/A</p>',
                unsafe_allow_html=True,
            )
    with col2:
        st.metric("Confidence", f"{confidence}%" if confidence is not None else "N/A")
    with col3:
        summary = result.get("summary", {})
        st.metric("Scraping Method", summary.get("scraping_method", "N/A"))
    scraping_info = summary.get("insights", {}).get("scraping", {})
    scraping_incomplete = scraping_info.get("status") == "incomplete" or summary.get("scraping_incomplete")
    if scraping_incomplete:
        reason = scraping_info.get("reason") or summary.get("scraping_incomplete_reason") or "Description could not be captured from the source."
        st.warning(
            "⚠️ Content scrape incomplete — "
            f"{reason} Please open the job posting directly in your browser to verify details."
        )
    
    # Source info
    st.subheader("📋 Source Information")
    col1, col2 = st.columns(2)
    source = result.get("source", {})
    with col1:
        st.write(f"**Title:** {source.get('title', 'N/A')}")
        st.write(f"**Company:** {source.get('company', 'N/A')}")
    with col2:
        st.write(f"**URL:** {source.get('url', 'N/A')}")
        st.write(f"**Domain:** {summary.get('source_domain', 'N/A')}")

    # Flags
    display_flags(result.get("flags", {}))
    
    # Company Intelligence
    if summary.get("company_intel"):
        display_company_intel(summary["company_intel"])
    
    # Detailed Summary
    with st.expander("📊 Detailed Analysis Summary"):
        col1, col2 = st.columns(2)
        with col1:
            render_metric(
                "Content Score",
                summary.get("content_score"),
                disabled=scraping_incomplete,
                placeholder="Not evaluated (scrape incomplete)",
            )
            render_metric("Verification Score", summary.get("verification_score"))
            render_metric("Financial Score", summary.get("financial_score"))
        with col2:
            token_placeholder = "Scrape incomplete" if scraping_incomplete else "N/A"
            render_metric(
                "Token Count",
                summary.get("token_count"),
                disabled=scraping_incomplete,
                placeholder=token_placeholder,
            )
            render_metric(
                "Content Token Count",
                summary.get("content_token_count"),
                disabled=scraping_incomplete,
                placeholder=token_placeholder,
            )
            scraped_at = summary.get("scraped_at", "N/A")
            if scraped_at != "N/A":
                st.metric("Scraped At", scraped_at[:19])
        
        st.write("**Flag Summary:**")
        st.json(summary.get("flag_summary", {}))
        
        if summary.get("insights"):
            st.write("**Insights:**")
            st.json(summary["insights"]) 


def main():
    """Main Streamlit app."""
    st.title("🔍 Job Posting Verifier")
    st.markdown(
        "Verify job postings for red flags, scams, and legitimacy signals."
    )
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        st.info(
            "This tool analyzes job postings using open-source intelligence, "
            "content analysis, and risk scoring."
        )
        
        if st.session_state.results_history:
            if st.button("📜 Clear History"):
                st.session_state.results_history = []
                st.rerun()
    
    # Main input
    st.subheader("Enter Job Posting URL")
    url_input = st.text_input(
        "Paste the job posting URL:",
        placeholder="https://example.com/jobs/12345",
        key="url_input",
    )
    
    col1, col2 = st.columns([3, 1])
    with col1:
        analyze_btn = st.button("🔍 Analyze Posting", key="analyze_btn")
    with col2:
        st.write("")  # Spacer for alignment
    
    # Analysis
    if analyze_btn and url_input.strip():
        with st.spinner("🔄 Analyzing posting..."):
            try:
                result = st.session_state.orchestrator.process_job(url_input.strip())
                display_result(result)
                
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
            except Exception as exc:
                st.error(f"❌ Analysis failed: {str(exc)}")
                logger.exception("Analysis error")
    elif analyze_btn:
        st.warning("⚠️ Please enter a URL to analyze.")
    
    # History sidebar
    if st.session_state.results_history:
        with st.sidebar:
            st.subheader("📚 Recent Analyses")
            for i, hist_item in enumerate(st.session_state.results_history[:10]):
                verdict_label = hist_item.get("verdict", "unknown")
                emoji = get_verdict_emoji(verdict_label)
                rs = hist_item.get("risk_score")
                # Decide color and display value for possibly-missing risk score
                try:
                    rs_val = int(rs) if rs is not None else None
                except Exception:
                    rs_val = None

                if rs_val is None:
                    risk_color = "gray"
                    rs_display = "N/A"
                else:
                    risk_color = "red" if rs_val >= 70 else "orange" if rs_val >= 40 else "green"
                    rs_display = f"{rs_val}"

                with st.expander(
                    f"{emoji} {verdict_label.replace('_', ' ').title()} ({rs_display}/100) - {hist_item.get('timestamp', '')}"
                ):
                    st.write(f"**URL:** {hist_item.get('url', 'N/A')}")
                    if st.button("🔄 Re-analyze", key=f"reanalyze_{i}"):
                        st.session_state.url_input = hist_item["url"]
                        st.rerun()


if __name__ == "__main__":
    main()
