"""Settings from the environment, with the project's ``.env`` loaded first.

Real environment variables win over the file, so a deployment can override
anything a developer's ``.env`` says.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def load_env() -> Path | None:
    """Load the nearest ``.env`` — in the current directory or a parent —
    into ``os.environ``. Returns its path, or ``None`` when there is none."""
    found = find_dotenv(usecwd=True)
    if not found:
        return None
    load_dotenv(found)
    return Path(found)


def data_dir() -> Path:
    """``LOVIA_MU_DATA``, default ``./data``."""
    return Path(os.environ.get("LOVIA_MU_DATA") or "data")
