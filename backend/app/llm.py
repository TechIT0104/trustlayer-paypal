"""LLM access with automatic failover: Groq -> Gemini -> local Ollama.

Every call asks for JSON, has a hard timeout, and falls through to the next provider on
any error (rate limit, 503 "high demand", timeout, bad JSON). Results are cached by
prompt so repeated demo clicks do not burn free-tier quota.
"""
import hashlib
import json
import re
import threading
import time

import httpx

from . import config

_cache: dict[str, dict] = {}
_clock = threading.Lock()
_http = httpx.Client(timeout=httpx.Timeout(30.0, connect=8.0))
stats = {"calls": 0, "by_provider": {}, "failures": {}}


class LLMUnavailable(Exception):
    pass


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _groq(system: str, user: str, temperature: float) -> tuple[dict, str]:
    if not config.GROQ_API_KEY:
        raise LLMUnavailable("no GROQ_API_KEY")
    r = _http.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        json={"model": config.GROQ_MODEL, "temperature": temperature,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        timeout=25.0,
    )
    r.raise_for_status()
    return _parse_json(r.json()["choices"][0]["message"]["content"]), config.GROQ_MODEL


def _gemini(system: str, user: str, temperature: float) -> tuple[dict, str]:
    if not config.GEMINI_API_KEY:
        raise LLMUnavailable("no GEMINI_API_KEY")
    r = _http.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": config.GEMINI_API_KEY},
        json={"systemInstruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": user}]}],
              "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"}},
        timeout=25.0,
    )
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return _parse_json("".join(p.get("text", "") for p in parts)), config.GEMINI_MODEL


def _ollama(system: str, user: str, temperature: float) -> tuple[dict, str]:
    r = _http.post(
        f"{config.OLLAMA_URL}/api/chat",
        json={"model": config.OLLAMA_MODEL, "stream": False, "format": "json",
              "options": {"temperature": temperature},
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        timeout=90.0,
    )
    r.raise_for_status()
    return _parse_json(r.json()["message"]["content"]), f"ollama/{config.OLLAMA_MODEL}"


PROVIDERS = {"groq": _groq, "gemini": _gemini, "ollama": _ollama}


def complete_json(system: str, user: str, temperature: float = 0.1, use_cache: bool = True,
                  providers: list[str] | None = None) -> dict:
    """Returns {"data": <parsed JSON>, "provider": str, "model": str, "latency_ms": int, "cached": bool}."""
    order = providers or config.LLM_PROVIDERS
    key = hashlib.sha256(json.dumps([system, user, temperature, order]).encode()).hexdigest()
    if use_cache:
        with _clock:
            if key in _cache:
                return {**_cache[key], "cached": True}
    errors = []
    for name in order:
        fn = PROVIDERS.get(name)
        if not fn:
            continue
        t0 = time.time()
        try:
            data, model = fn(system, user, temperature)
        except Exception as e:  # noqa: BLE001 - any provider failure means "try the next one"
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
            stats["failures"][name] = stats["failures"].get(name, 0) + 1
            continue
        out = {"data": data, "provider": name, "model": model,
               "latency_ms": int((time.time() - t0) * 1000), "cached": False}
        stats["calls"] += 1
        stats["by_provider"][name] = stats["by_provider"].get(name, 0) + 1
        with _clock:
            _cache[key] = out
        return out
    raise LLMUnavailable("; ".join(errors) or "no providers configured")
