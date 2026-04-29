"""
Supabase client factory for the pipeline.

Uses the service role key from config so inserts bypass Row Level Security,
which is required for server-side ETL writes to tables like ``statcast_pitches``
(see SCHEMA.md in the Next.js app repo).
"""

from functools import lru_cache

from supabase import Client, create_client

import config


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Return a singleton Supabase client configured for server-side writes."""

    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env "
            "(see config.py)."
        )

    return create_client(
        config.SUPABASE_URL,
        config.SUPABASE_SERVICE_ROLE_KEY,
    )
