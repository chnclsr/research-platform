from __future__ import annotations

import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./.pytest-research.db"
os.environ["TESTING"] = "true"
os.environ["LLM_PROVIDER"] = "deterministic"
os.environ["DOMAIN_DELAY_S"] = "0"


def pytest_sessionstart(session):
    Path(".pytest-research.db").unlink(missing_ok=True)


