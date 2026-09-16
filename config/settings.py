"""
Central configuration.
Loads everything from environment variables (via a .env file in dev).

Pattern reused from slack-pagerduty-incident-bot3's config/settings.py —
one place, no scattered os.getenv calls elsewhere in the codebase.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------

SLACK_BOT_TOKEN = _get("SLACK_BOT_TOKEN", required=True)
SLACK_SIGNING_SECRET = _get("SLACK_SIGNING_SECRET", required=True)
SLACK_APP_TOKEN = _get("SLACK_APP_TOKEN", required=True)  # xapp-... for Socket Mode

# The dedicated alerts-only channel PagerDuty's Slack integration posts
# into. NOT the human channel from the old project — see CLAUDE.md's
# Trigger section for why a dedicated channel matters here.
SLACK_ALERTS_CHANNEL = _get("SLACK_ALERTS_CHANNEL", default="sre-alerts")

# ---------------------------------------------------------------------------
# Confluence (used by sync/*.py, not directly by the agent — the agent
# only ever reads the local vector DB via agent/tools/retrieve_sop.py)
# ---------------------------------------------------------------------------

CONFLUENCE_BASE_URL = _get("CONFLUENCE_BASE_URL")
CONFLUENCE_EMAIL = _get("CONFLUENCE_EMAIL")
CONFLUENCE_API_TOKEN = _get("CONFLUENCE_API_TOKEN")
CONFLUENCE_SPACE_KEY = _get("CONFLUENCE_SPACE_KEY")

# ---------------------------------------------------------------------------
# PagerDuty (REST API -- reused as-is from the old project; still fires
# independently via Alertmanager, the agent doesn't call this itself)
# ---------------------------------------------------------------------------

PAGERDUTY_API_KEY = _get("PAGERDUTY_API_KEY")
PAGERDUTY_SERVICE_ID = _get("PAGERDUTY_SERVICE_ID")
PAGERDUTY_FROM_EMAIL = _get("PAGERDUTY_FROM_EMAIL")

# ---------------------------------------------------------------------------
# LLM provider (used by the LangGraph agent)
# ---------------------------------------------------------------------------

LLM_PROVIDER = _get("LLM_PROVIDER", default="groq")
GROQ_API_KEY = _get("GROQ_API_KEY")
# llama-3.3-70b-versatile was deprecated on Groq's free/developer tier
# (June 2026) -- openai/gpt-oss-120b is Groq's own recommended replacement.
GROQ_MODEL = _get("GROQ_MODEL", default="openai/gpt-oss-120b")