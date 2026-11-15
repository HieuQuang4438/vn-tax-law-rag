import pytest

import src.config as config
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


def _required_numbered():
    found = getattr(config, "required_numbered", None)
    assert found is not None, "src.config has no required_numbered"
    return found


def _set_numbered(monkeypatch, name, values):
    for n in range(1, 10):
        monkeypatch.delenv(f"{name}_{n}", raising=False)
    for n, value in enumerate(values, 1):
        if value is not None:
            monkeypatch.setenv(f"{name}_{n}", value)


def test_numbered_keys_are_read_in_order(monkeypatch):
    _set_numbered(monkeypatch, "SCAFFOLD_KEY", ["a", "b", "c"])
    assert _required_numbered()("SCAFFOLD_KEY") == ("a", "b", "c")


def test_numbered_keys_stop_at_the_first_gap(monkeypatch):
    _set_numbered(monkeypatch, "SCAFFOLD_KEY", ["a", None, "c"])
    assert _required_numbered()("SCAFFOLD_KEY") == ("a",)


def test_numbered_keys_stop_at_an_empty_value(monkeypatch):
    _set_numbered(monkeypatch, "SCAFFOLD_KEY", ["a", "", "c"])
    assert _required_numbered()("SCAFFOLD_KEY") == ("a",)


@pytest.mark.parametrize("values", [[], [""], [None, "b"]])
def test_numbered_keys_need_the_first(monkeypatch, values):
    _set_numbered(monkeypatch, "SCAFFOLD_KEY", values)
    with pytest.raises(RuntimeError, match="SCAFFOLD_KEY_1"):
        _required_numbered()("SCAFFOLD_KEY")


def test_the_google_keys_are_numbered():
    keys = getattr(config, "GOOGLE_API_KEYS", None)
    assert keys == ("dummy-key-for-tests",)
