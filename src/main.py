"""Entrypoint. Run with `python -m src.main`."""

from src.config import LLM_MODEL

APP_NAME = "vn-tax-law-rag"


def main() -> None:
    print(f"{APP_NAME} up. Model: {LLM_MODEL}")


if __name__ == "__main__":
    main()
