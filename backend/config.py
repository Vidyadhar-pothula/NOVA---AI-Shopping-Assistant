"""
NOVA Backend Configuration
Loads sensitive keys from the project-root .env file, then environment variables.
"""
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ENV_PATH = _ROOT / ".env"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=True)
        return
    except ImportError:
        pass
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            os.environ[key] = value


_load_env_file(_ENV_PATH)

# ── Razorpay ─────────────────────────────────────────────────────────────────
RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", "rzp_test_placeholder")
RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", "placeholder_secret")

# ── LLM ──────────────────────────────────────────────────────────────────────
NOVA_LLM_MODEL: str = os.getenv("NOVA_LLM_MODEL", "llama3.1:8b")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── App ───────────────────────────────────────────────────────────────────────
APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

# ── Commerce APIs ─────────────────────────────────────────────────────────────
SERP_API_KEY: str = os.getenv("SERP_API_KEY", "")
COMMERCE_API_KEY: str = os.getenv("COMMERCE_API_KEY", "")
RAPIDAPI_KEY: str = os.getenv("RAPIDAPI_KEY", "")

# ── Email SMTP Config ────────────────────────────────────────────────────────
SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "pothulavidyadhar@gmail.com")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "fbxkjjhbyzahmxwq")
SMTP_FROM: str = os.getenv("SMTP_FROM", "pothulavidyadhar@gmail.com")


