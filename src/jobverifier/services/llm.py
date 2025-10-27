from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

try:  # Optional dependency
    from mistralai import Mistral  # type: ignore[import]
    _MISTRAL_AVAILABLE = True
except ImportError:  # pragma: no cover - environment without package
    Mistral = None  # type: ignore[assignment]
    _MISTRAL_AVAILABLE = False

from ..config import MISTRAL_API_KEY

logger = logging.getLogger(__name__)

_CLIENT: Optional[Any] = None


def _get_client() -> Optional[Any]:
    global _CLIENT
    if _CLIENT is None:
        if not MISTRAL_API_KEY:
            logger.warning("❌ Mistral API key not configured; LLM features disabled")
            return None
        if not _MISTRAL_AVAILABLE:
            logger.warning("❌ mistralai package not installed; LLM features disabled")
            return None
        try:
            _CLIENT = Mistral(api_key=MISTRAL_API_KEY)
            logger.info("✅ Mistral client initialized successfully with API key: %s***", MISTRAL_API_KEY[:8])
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


def llm_available() -> bool:
    """Return True if the Mistral client can be used."""

    return _MISTRAL_AVAILABLE and bool(MISTRAL_API_KEY)
