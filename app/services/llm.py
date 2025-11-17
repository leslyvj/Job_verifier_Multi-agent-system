from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import requests

try:  # Optional dependency
    from mistralai import Mistral  # type: ignore[import]

    _MISTRAL_AVAILABLE = True
except ImportError:  # pragma: no cover - environment without package
    Mistral = None  # type: ignore[assignment]
    _MISTRAL_AVAILABLE = False

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()
MISTRAL_API_KEY = settings.mistral_api_key
PROVIDER = settings.llm_provider.lower()

_CLIENT: Optional[Any] = None
_OLLAMA_AVAILABLE: Optional[bool] = None


def _get_client() -> Optional[Any]:
    global _CLIENT
    if PROVIDER != "mistral":
        return None
    if _CLIENT is None:
        if not MISTRAL_API_KEY:
            logger.warning("❌ Mistral API key not configured; LLM features disabled")
            return None
        if not _MISTRAL_AVAILABLE:
            logger.warning("❌ mistralai package not installed; LLM features disabled")
            return None
        try:
            _CLIENT = Mistral(api_key=MISTRAL_API_KEY)
            logger.info(
                "✅ Mistral client initialized successfully with API key: %s***",
                MISTRAL_API_KEY[:8],
            )
        except Exception as exc:  # pragma: no cover - network/creds errors
            logger.error("❌ Failed to initialize Mistral client: %s", exc)
            _CLIENT = None
    return _CLIENT


def chat(
    prompt: str,
    *,
    system_prompt: Optional[str] = None,
    model: str = "mistral-small-latest",
    temperature: float = 0.2,
    max_tokens: int = 512,
) -> Optional[str]:
    if PROVIDER == "ollama":
        return _ollama_chat(
            prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    client = _get_client()
    if not client or not _MISTRAL_AVAILABLE:
        logger.warning("❌ LLM call skipped - client not available")
        return None

    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        logger.info("🤖 Calling Mistral API with model: %s", model)
        response = client.chat.complete(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        logger.info("✅ Mistral API call successful")
    except Exception as exc:  # pragma: no cover - remote call
        logger.error("❌ Mistral chat call failed: %s", exc)
        return None

    content = _extract_content(response)
    return content.strip() if content else None


def structured_chat(
    prompt: str,
    *,
    system_prompt: Optional[str] = None,
    model: str = "mistral-small-latest",
    temperature: float = 0.2,
    max_tokens: int = 512,
) -> Optional[Dict[str, Any]]:
    raw = chat(
        prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.debug("LLM response was not valid JSON: %s", raw)
        return None


def _extract_content(response: Any) -> str:
    chunks: List[str] = []
    for choice in getattr(response, "choices", []):
        message = getattr(choice, "message", None)
        if not message:
            continue
        content = getattr(message, "content", None)
        if isinstance(content, list):
            for item in content:
                text = getattr(item, "text", None)
                if text:
                    chunks.append(text)
        elif content:
            chunks.append(str(content))
    return "".join(chunks)


def _ollama_chat(
    prompt: str,
    *,
    system_prompt: Optional[str],
    model: str,
    temperature: float,
    max_tokens: int,
) -> Optional[str]:
    if not _ensure_ollama_available():
        logger.warning("❌ LLM call skipped - Ollama endpoint unavailable")
        return None

    resolved_model = settings.ollama_model or model
    payload: Dict[str, Any] = {
        "model": resolved_model,
        "stream": False,
        "messages": [],
        "options": {
            "temperature": temperature,
        },
    }
    if max_tokens:
        payload["options"]["num_predict"] = max_tokens

    if system_prompt:
        payload["messages"].append({"role": "system", "content": system_prompt})
    payload["messages"].append({"role": "user", "content": prompt})

    try:
        logger.info(
            "🤖 Calling Ollama model '%s' at %s",
            resolved_model,
            settings.ollama_host,
        )
        response = requests.post(
            f"{settings.ollama_host.rstrip('/')}/api/chat",
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("❌ Ollama chat call failed: %s", exc)
        return None

    data = response.json()
    message = data.get("message") or {}
    content = message.get("content")
    return str(content).strip() if content else None


def _ensure_ollama_available() -> bool:
    global _OLLAMA_AVAILABLE
    if _OLLAMA_AVAILABLE is not None:
        return _OLLAMA_AVAILABLE
    try:
        ping = requests.get(
            f"{settings.ollama_host.rstrip('/')}/api/tags",
            timeout=5,
        )
        _OLLAMA_AVAILABLE = ping.ok
        if _OLLAMA_AVAILABLE:
            logger.info("✅ Ollama endpoint detected at %s", settings.ollama_host)
        else:
            logger.warning(
                "❌ Ollama endpoint responded with status %s", ping.status_code
            )
    except requests.RequestException as exc:
        logger.warning("❌ Ollama endpoint unreachable: %s", exc)
        _OLLAMA_AVAILABLE = False
    return _OLLAMA_AVAILABLE


def llm_available() -> bool:
    """Return True if the configured LLM provider can be used."""

    if PROVIDER == "ollama":
        return _ensure_ollama_available()
    return _MISTRAL_AVAILABLE and bool(MISTRAL_API_KEY)
