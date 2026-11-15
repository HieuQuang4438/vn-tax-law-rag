"""Single place this repo reads the environment — CONVENTIONS.md §3."""

import os

from dotenv import load_dotenv

load_dotenv()


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def required_numbered(name: str) -> tuple[str, ...]:
    """`<name>_1`, `<name>_2`, ... up to the first missing or empty one; `<name>_1` is required (#13)."""
    values = [required(f"{name}_1")]
    while value := os.getenv(f"{name}_{len(values) + 1}"):
        values.append(value)
    return tuple(values)


GOOGLE_API_KEYS = required_numbered("GOOGLE_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
