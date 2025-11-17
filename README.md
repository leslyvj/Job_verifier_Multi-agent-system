# Job Verifier Multi-Agent System

Production-ready Python project that analyzes job postings for potential fraud using a LangGraph workflow, rule-based heuristics, OSINT enrichment, and optional Mistral LLM support. A Streamlit dashboard offers an interactive review experience while the CLI provides quick verdicts.

## Project Layout

```
app/
	agents/           # Core agent implementations
	config/           # Environment-backed settings
	services/         # External service clients (scraper, LLM, analysis)
	utils/            # Shared constants, prompts, and logging helpers
	workflows/        # LangGraph pipeline orchestration
	main.py           # CLI entry point
tests/              # Placeholder tests ready for expansion
app.py              # Streamlit dashboard entry
main.py             # Thin wrapper delegating to app.main
```

The project is intentionally minimal—only the `app` package (and thin wrappers for the CLI and Streamlit UI) remain.

## Prerequisites

- Python 3.12+
- Optional: Chromium browser (Playwright) and ChromeDriver (Selenium) for JS-heavy scraping
- Optional: Mistral API key to enable LLM-backed features

Install dependencies and, if needed, browser drivers:

```bash
pip install -r requirements.txt
python -m playwright install chromium  # optional JS-rendering support
```

## Configuration

Create a `.env` file in the project root to configure LLM access:

```ini
# Default: hosted Mistral
LLM_PROVIDER=mistral
MISTRAL_API_KEY=your_mistral_key_here

# Optional: switch to a local Ollama model
# LLM_PROVIDER=ollama
# OLLAMA_MODEL=mistral
# OLLAMA_HOST=http://localhost:11434
```

The application will automatically disable LLM features when the key or package is missing.

### Using a Local Ollama Model

1. Install [Ollama](https://ollama.com/download) and run it locally (the default API endpoint is `http://localhost:11434`).
2. Pull or create the model you want, for example `ollama pull mistral` or `ollama pull llama3`.
3. Set `LLM_PROVIDER=ollama` and `OLLAMA_MODEL` to the name you pulled.
4. Restart the CLI or Streamlit app; the agents will send chat requests to the local Ollama endpoint instead of the hosted Mistral API.

## Usage

- **CLI Analyzer:** `python main.py` then provide a job URL when prompted.
- **Streamlit Dashboard:** `streamlit run app.py` and open the provided local URL.

Both entry points surface the orchestrated verdict, confidence, risk score, agent flags, and supporting insights.

## Testing

A placeholder test resides in `tests/test_placeholder.py`; add unit or integration coverage here as the project evolves.

## Development Notes

- Agents share prompts, constants, and logging via `app.utils` to ensure consistent behavior.
- The orchestrator in `app.workflows` assembles agents through LangGraph; adjust the graph to experiment with new steps.
- `.env` remains ignored by git for safety; configure environment variables per deployment.

## Contributing

1. Fork or clone the repository.
2. Create a virtual environment and install dependencies.
3. Implement or adjust features under the `app/` package.
4. Add or update tests under `tests/` as coverage grows.
5. Submit a pull request describing the motivation and verification steps.

Feedback and contributions are welcome—feel free to open issues or propose enhancements.
