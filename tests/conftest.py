"""`src.config` fails loudly at import when a required var is absent — §3.

Tests therefore need the required vars present before `src.config` is imported.
Values are dummies; no test may reach a real service.
"""

import os

os.environ.setdefault("GOOGLE_API_KEY", "dummy-key-for-tests")
os.environ.setdefault("GOOGLE_API_KEY_1", "dummy-key-for-tests")
# An empty second key ends the list, so the keys in a local `.env` are not loaded.
os.environ["GOOGLE_API_KEY_2"] = ""
