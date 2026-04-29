"""
Central configuration for the WARroom Statcast pipeline.

Loads secrets from ``.env`` in this directory. See SCHEMA.md (in the repo) for
table definitions used by the loaders.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Always load .env from the pipeline directory regardless of
# where the script is called from
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# -----------------------------------------------------------------------------
# Supabase (writes use service role — bypasses RLS per Supabase design)
# -----------------------------------------------------------------------------
SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY: str | None = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# -----------------------------------------------------------------------------
# Game-day polling window (US Eastern — aligns with typical MLB schedule)
# -----------------------------------------------------------------------------
GAME_HOURS = {
    "start_hour": 12,
    "end_hour": 23,
}

# How often the scheduler should consider a run (must match cron minute step).
POLL_INTERVAL_MINUTES = 5
