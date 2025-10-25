# Job Verifier Multi-Agent System

A Python-based multi-agent workflow that analyzes job postings for potential fraud signals using rule-based heuristics, OSINT checks, and optional Mistral LLM assistance. The project includes a Streamlit dashboard for interactive reviews and can be run headlessly from the CLI.

## Features

- **Agent Orchestrator** built on LangGraph with data acquisition, content analysis, source verification, financial risk, and company intelligence steps.
- **Scraping engine** with requests fallback to Playwright/Selenium for JavaScript-rendered postings.
- **Company intelligence** enrichment pulling LinkedIn, press mentions, SEC filings, and HR contact signals.
- **Mistral LLM integration** (optional) for language quality, contact filtering, and narrative summaries.
- **Streamlit UI** that presents verdicts, risk scores, flags, and insight details with a history sidebar.

## Requirements

- Python 3.12+
- Recommended: Chromium (for Playwright) and ChromeDriver (for Selenium fallback)
- Optional: Mistral API key for LLM-powered features

Install dependencies:

```bash
pip install -r requirements.txt
python -m playwright install chromium  # if Playwright is enabled
```

## Environment Variables

Create a `.env` file at the project root:

```ini
MISTRAL_API_KEY=your_mistral_key_here  # optional; omit to disable LLM calls
```

The application degrades gracefully when the key is absent or the `mistralai` SDK is not installed.

## Running the CLI Analyzer

Use the orchestrator to analyze a single job posting:

```bash
python main.py
# Enter the job URL when prompted
```

The CLI prints a verdict, risk score, flags, and a compact summary dictionary.

## Running the Streamlit Frontend

Launch the dashboard:

```bash
streamlit run app.py
```

Open the provided URL in your browser (default: <http://localhost:8501>) and paste job posting URLs to view detailed analysis results. The app stores recent history in the session and highlights scraping issues, risk flags, and company intelligence.

## Development Notes

- The code lives under `src/jobverifier/` following a modular layout for agents, services, and pipeline definitions.
- Browser automation is optional; enable it by ensuring Playwright/Selenium dependencies are installed. The data acquisition agent automatically attempts JS rendering on trusted domains when descriptions are too short.
- For reproducible deployments, keep `.env` out of version control (see `.gitignore`).

## Contributing / Extending

1. Fork or clone the repository.
2. Create a virtual environment and install requirements.
3. Run unit or integration tests (if added) before submitting changes.
4. Enhance agents by adding new heuristics or integrating additional data sources.

Feel free to open issues or submit pull requests for bug fixes, improvements, or new agent ideas.
