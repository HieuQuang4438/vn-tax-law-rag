"""`src.config` fails loudly at import when a required var is absent — §3.

Tests therefore need the required vars present before `src.config` is imported.
Values are dummies; no test may reach a real service.
"""

import os

os.environ.setdefault("GOOGLE_API_KEY", "dummy-key-for-tests")
