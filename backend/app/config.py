"""Settings loaded from the project .env (local) or real environment variables (Render)."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


PAYPAL_CLIENT_ID = _env("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = _env("PAYPAL_CLIENT_SECRET")
PAYPAL_BASE_URL = _env("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
# Set after registering the webhook (scripts/register_webhook.py); enables signature verification.
PAYPAL_WEBHOOK_ID = _env("PAYPAL_WEBHOOK_ID")
# Demo-only endpoints (reset, tamper simulation). Turn off for anything public-facing beyond a demo.
DEMO_MODE = _env("DEMO_MODE", "true").lower() in ("1", "true", "yes")

GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_MODEL = _env("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-flash-lite-latest")
OLLAMA_URL = _env("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "mistral")
# Comma-separated provider order. Ollama only helps when running locally.
LLM_PROVIDERS = [p.strip() for p in _env("LLM_PROVIDERS", "groq,gemini,ollama").split(",") if p.strip()]

# Demo-friendly cooling-off window for paused payments (real-world default would be 24h).
COOLING_OFF_SECONDS = int(_env("COOLING_OFF_SECONDS", "120"))
PLATFORM_FEE_PCT = float(_env("PLATFORM_FEE_PCT", "5"))
DB_PATH = pathlib.Path(_env("DB_PATH", str(ROOT / "backend" / "trustlayer.db")))
CURRENCY = "USD"
