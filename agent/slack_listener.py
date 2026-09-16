"""
Slack Alert Listener
=====================

Watches the dedicated alerts-only channel (SLACK_ALERTS_CHANNEL) for
messages posted by PagerDuty's Slack integration, and responds with:
  1. An immediate acknowledgment (so a human sees the bot is on it --
     the agent loop below takes a few seconds, this fires first)
  2. The LangGraph agent's synthesized diagnosis (agent/graph.py) --
     calls check_site_health, check_k8s_workload, and retrieve_sop,
     correlates the results, and writes one clear conclusion, rather
     than a fixed template of raw tool output.

Same Socket Mode / outbound-only pattern as slack-pagerduty-incident-bot3's
bot/slack_handler.py — reused deliberately, see CLAUDE.md's Trigger
section for why this project's trigger ended up being a Slack message
too, not an inbound webhook.

Detection logic differs from the old project though: the old bot ignored
ALL bot messages (since its trigger was always a human). This bot's
trigger IS a bot message (PagerDuty's Slack app posting an incident) — so
here we specifically listen for bot-posted messages in the alerts
channel, not human ones.
"""
from __future__ import annotations

import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config.settings import (
    SLACK_ALERTS_CHANNEL,
    SLACK_APP_TOKEN,
    SLACK_BOT_TOKEN,
    SLACK_SIGNING_SECRET,
)
from agent.graph import diagnose

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)

_alerts_channel_id: str | None = None  # resolved once, cached


def _resolve_alerts_channel_id() -> str | None:
    """
    Slack events give us a channel ID, but SLACK_ALERTS_CHANNEL in .env
    is a human-readable name (e.g. "sre-alerts") -- resolve it once at
    startup rather than on every message.
    """
    global _alerts_channel_id
    if _alerts_channel_id is not None:
        return _alerts_channel_id

    try:
        cursor = None
        while True:
            resp = app.client.conversations_list(
                types="public_channel,private_channel", cursor=cursor, limit=200
            )
            for ch in resp.get("channels", []):
                if ch.get("name") == SLACK_ALERTS_CHANNEL:
                    _alerts_channel_id = ch["id"]
                    logger.info(
                        "Resolved #%s to channel ID %s", SLACK_ALERTS_CHANNEL, _alerts_channel_id
                    )
                    return _alerts_channel_id
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to resolve alerts channel ID: %s", exc)

    logger.error(
        "Could not find channel #%s -- is the bot invited to it? "
        "Falling back to matching by name on every event (slower).",
        SLACK_ALERTS_CHANNEL,
    )
    return None


def _reply(channel_id: str, thread_ts: str, text: str) -> None:
    try:
        app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=text,
            mrkdwn=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to post reply: %s", exc)


@app.event("message")
def handle_alert_message(event: dict, logger: logging.Logger) -> None:  # type: ignore[override]
    """
    Guard conditions (silently ignored):
    - Not in the alerts channel
    - Thread replies (only top-level messages -- i.e. new incidents -- trigger the flow)
    - Messages NOT from a bot (a human chatting in the alerts channel
      shouldn't trigger a full diagnostic flow -- this channel is meant
      to be alerts-only, but don't assume that's perfectly enforced)
    """
    channel_id: str = event.get("channel", "")
    ts: str = event.get("ts", "")
    text: str = event.get("text", "").strip()

    if event.get("thread_ts") and event["thread_ts"] != event.get("ts"):
        return  # thread reply, not a new incident

    if not (channel_id and ts and text):
        return

    resolved_id = _resolve_alerts_channel_id()
    if resolved_id:
        if channel_id != resolved_id:
            return
    else:
        # Fallback path if channel resolution failed at startup -- best
        # effort, logs a warning so this doesn't fail silently forever.
        logger.warning("Channel ID resolution unavailable, processing message without channel filter.")

    if not event.get("bot_id"):
        logger.info("Ignoring non-bot message in alerts channel (not a PagerDuty post).")
        return

    logger.info("Detected alert message in #%s: %s", SLACK_ALERTS_CHANNEL, text[:150])

    # 1. Immediate acknowledgment -- the agent loop below takes a few
    #    seconds (multiple tool calls + LLM synthesis), so this fires
    #    first so on-call sees the bot is working on it right away.
    _reply(
        channel_id, ts,
        ":robot_face: Incident detected — investigating now...",
    )

    # 2. Run the actual LangGraph agent -- calls check_site_health,
    #    check_k8s_workload, and retrieve_sop, correlates the results,
    #    and returns one synthesized conclusion.
    try:
        diagnosis = diagnose(text)
    except Exception as exc:  # noqa: BLE001
        logger.error("Agent diagnosis failed: %s", exc)
        diagnosis = (
            f":warning: Diagnosis failed to complete: {exc}\n"
            f"Falling back to manual investigation for this one."
        )

    _reply(channel_id, ts, diagnosis)


def main() -> None:
    logger.info("Resolving alerts channel...")
    _resolve_alerts_channel_id()
    logger.info("Starting SRE Diagnostic Agent (Socket Mode)...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    main()