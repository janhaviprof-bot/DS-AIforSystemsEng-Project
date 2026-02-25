# config.py - Load .env from common locations, export API keys

from __future__ import annotations

from pathlib import Path
import os
import logging

from dotenv import find_dotenv, load_dotenv

_log = logging.getLogger(__name__)


def _load_env_files() -> list[Path]:
    """
    Load .env from likely locations.

    Why: Shiny apps can be launched from different working directories (or restarted),
    so relying on only cwd or only one fixed relative path makes keys "disappear".
    """

    loaded: list[Path] = []
    seen: set[Path] = set()

    # 1) Whatever python-dotenv finds from cwd (walks up).
    try:
        found = find_dotenv(filename=".env", usecwd=True)
    except Exception:
        found = ""
    if found:
        p = Path(found).resolve()
        if p not in seen and p.exists():
            load_dotenv(p, override=False)
            loaded.append(p)
            seen.add(p)

    # 2) Walk up from this file's directory (AppV1) to repo root.
    here = Path(__file__).resolve()
    for parent in [here.parent] + list(here.parents):
        p = (parent / ".env").resolve()
        if p in seen:
            continue
        if p.exists():
            load_dotenv(p, override=False)
            loaded.append(p)
            seen.add(p)

    # 3) Finally, try a plain load (cwd only) without overriding existing env.
    load_dotenv(override=False)
    return loaded


_LOADED_ENV_PATHS = _load_env_files()
if _LOADED_ENV_PATHS:
    _log.info("Loaded .env from: %s", ", ".join(str(p) for p in _LOADED_ENV_PATHS))
else:
    _log.warning("No .env file found via cwd or parent search; API keys may be unset.")

NYT_API_KEY = os.getenv("NYT_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not (NYT_API_KEY and str(NYT_API_KEY).strip()):
    _log.warning("NYT_API_KEY is missing or empty (checked environment + loaded .env files).")
if not (OPENAI_API_KEY and str(OPENAI_API_KEY).strip()):
    _log.warning("OPENAI_API_KEY is missing or empty (checked environment + loaded .env files).")

# NYT sections to fetch
NYT_SECTIONS = [
    "home",
    "business",
    "arts",
    "technology",
    "world",
    "politics",
]
