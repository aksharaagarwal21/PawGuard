"""LLM adapter for the pet-owner assistant: Gemini API (free tier) or Ollama (local open model), chosen by config.

`LLMError.code` is stable: not_configured, rate_limited ("try again shortly"), blocked (provider safety filter),
unreachable, bad_response. The API key travels in a header, never in the URL (so it never appears in logs).
"""

from dataclasses import dataclass
from typing import Literal

import httpx

from pawguard_api.settings import Settings

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class Turn:
    role: Role
    text: str


class LLMError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


def provider(s: Settings) -> str:
    if s.llm_provider == "gemini" and s.gemini_api_key and s.gemini_model:
        return "gemini"
    if s.llm_provider == "ollama" and s.ollama_url and s.ollama_model:
        return "ollama"
    return "off"


def generate(s: Settings, system: str, turns: list[Turn], *, max_tokens: int = 400) -> str:
    p = provider(s)
    if p == "gemini":
        return _gemini(s, system, turns, max_tokens)
    if p == "ollama":
        return _ollama(s, system, turns, max_tokens)
    raise LLMError("not_configured", "PAWGUARD_LLM_PROVIDER is off or incomplete")


def _gemini(s: Settings, system: str, turns: list[Turn], max_tokens: int) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "model" if t.role == "assistant" else "user", "parts": [{"text": t.text}]}
                     for t in turns],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
    }
    try:
        r = httpx.post(url, json=body, headers={"x-goog-api-key": s.gemini_api_key or ""}, timeout=30)
    except httpx.HTTPError as exc:
        raise LLMError("unreachable", "Gemini API not reachable") from exc
    if r.status_code == 429:
        raise LLMError("rate_limited", "Gemini free-tier limit reached")
    if r.status_code in (401, 403):
        raise LLMError("not_configured", "Gemini API key rejected")
    if r.status_code >= 400:
        raise LLMError("unreachable" if r.status_code >= 500 else "bad_response", f"Gemini HTTP {r.status_code}")
    try:
        data = r.json()
        if (data.get("promptFeedback") or {}).get("blockReason"):
            raise LLMError("blocked", "Gemini safety filter")
        cand = (data.get("candidates") or [{}])[0]
        if cand.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
            raise LLMError("blocked", "Gemini safety filter")
        text = "".join(part.get("text", "") for part in (cand.get("content") or {}).get("parts", []))
    except (ValueError, AttributeError, IndexError) as exc:
        raise LLMError("bad_response", "Unexpected Gemini response") from exc
    if not text.strip():
        raise LLMError("bad_response", "Empty Gemini response")
    return text


def _ollama(s: Settings, system: str, turns: list[Turn], max_tokens: int) -> str:
    body = {"model": s.ollama_model, "stream": False, "options": {"temperature": 0.3, "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}] + [{"role": t.role, "content": t.text} for t in turns]}
    try:
        r = httpx.post(f"{s.ollama_url.rstrip('/')}/api/chat", json=body, timeout=120)
    except httpx.HTTPError as exc:
        raise LLMError("unreachable", "Ollama is not running") from exc
    if r.status_code >= 400:
        raise LLMError("bad_response", f"Ollama HTTP {r.status_code}")
    try:
        text = r.json()["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise LLMError("bad_response", "Unexpected Ollama response") from exc
    if not str(text).strip():
        raise LLMError("bad_response", "Empty Ollama response")
    return str(text)
