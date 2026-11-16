"""`src.config` fails loudly at import when a required var is absent — §3.

Tests therefore need the required vars present before `src.config` is imported.
Values are dummies; no test may reach a real service. A live run (`pytest -m live`) is the one
exception: it sets nothing here, so `src.config` reads the local `.env` as the app does (#15).
"""

import os


def pytest_configure(config):
    if config.getoption("markexpr") == "live":
        return
    os.environ.setdefault("GOOGLE_API_KEY_1", "dummy-key-for-tests")
    # An empty second key ends the list, so the keys in a local `.env` are not loaded.
    os.environ["GOOGLE_API_KEY_2"] = ""
