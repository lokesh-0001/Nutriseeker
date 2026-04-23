import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or default


NUTRISEEKER_API_URL = get_env("NUTRISEEKER_API_URL", "http://localhost:8000")
OLLAMA_URL = get_env("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL_NAME = get_env("OLLAMA_MODEL_NAME", "llava")
USDA_API_KEY = get_env("USDA_API_KEY")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in (get_env("NUTRISEEKER_ALLOWED_ORIGINS", "*") or "*").split(",")
    if origin.strip()
]
USER_DB_PATH = get_env("USER_DB_PATH")
