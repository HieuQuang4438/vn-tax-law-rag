import pytest

from src.config import LLM_MODEL, required


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("SCAFFOLD_ABSENT_VAR", raising=False)
    with pytest.raises(RuntimeError, match="SCAFFOLD_ABSENT_VAR"):
        required("SCAFFOLD_ABSENT_VAR")


def test_empty_value_counts_as_missing(monkeypatch):
    monkeypatch.setenv("SCAFFOLD_EMPTY_VAR", "")
    with pytest.raises(RuntimeError):
        required("SCAFFOLD_EMPTY_VAR")


def test_optional_var_falls_back_to_default():
    assert LLM_MODEL
