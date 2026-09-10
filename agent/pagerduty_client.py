"""
PagerDuty Client
================

REUSE NOTE: copied as-is from the slack-pagerduty-incident-bot3 project
(bot/pagerduty_client.py). No changes made yet. This continues to fire
in parallel via Alertmanager directly per CLAUDE.md — the LangGraph
agent does not call this itself; paging stays independent of the
agent's diagnosis.

Creates and resolves PagerDuty incidents.

Incident creation uses PagerDuty's REST API:
    POST https://api.pagerduty.com/incidents

Incident resolution uses PagerDuty's Events API v2:
    POST https://events.pagerduty.com/v2/enqueue

The REST API returns the incident URL directly.

Duplicate handling:
    PagerDuty returns HTTP 400 with error code 2002 when an open
    incident with the same incident_key already exists on the service.

    Example:
    {
        "error": {
            "message": "Arguments Caused Error",
            "code": 2002,
            "errors": [
                "Open incident with matching dedup key already exists on this service"
            ]
        }
    }

    This is treated as an expected duplicate condition rather than
    a genuine API failure. The existing incident is looked up and
    reused.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PagerDuty endpoints
# ---------------------------------------------------------------------------

PD_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"
PD_REST_INCIDENTS_URL = "https://api.pagerduty.com/incidents"

REQUEST_TIMEOUT = 10  # seconds

# PagerDuty error code returned when an open incident with the same
# dedup/incident key already exists on the service.
PD_DUPLICATE_ERROR_CODE = 2002

PD_DUPLICATE_ERROR_TEXT = (
    "Open incident with matching dedup key already exists on this service"
)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _build_dedup_key(
    title: str,
    window_minutes: int = 24 * 60,
) -> str:
    """
    Build a stable deduplication key.

    Repeated reports with the same title within the same time window
    receive the same key, allowing the application to reuse the same
    PagerDuty incident.

    Args:
        title:
            Incident title.

        window_minutes:
            Length of the deduplication window.

            Default:
                24 hours.

            Example:
                60 -> one incident per title per hour.

    Returns:
        A deterministic PagerDuty incident key.
    """

    safe_title = (
        title[:50]
        .lower()
        .replace(" ", "-")
    )

    now = datetime.now(timezone.utc)

    bucket = int(
        now.timestamp() // (window_minutes * 60)
    )

    return f"incident-bot-{safe_title}-{bucket}"


# ---------------------------------------------------------------------------
# Duplicate error detection
# ---------------------------------------------------------------------------

def _is_duplicate_incident_error(
    response: requests.Response | None,
) -> bool:
    """
    Determine whether a PagerDuty HTTP response represents the
    expected duplicate-incident condition.

    PagerDuty returns HTTP 400 with a response similar to:

    {
        "error": {
            "message": "Arguments Caused Error",
            "code": 2002,
            "errors": [
                "Open incident with matching dedup key already exists on this service"
            ]
        }
    }

    We check both the PagerDuty error code and error message.

    Args:
        response:
            PagerDuty HTTP response.

    Returns:
        True if the response represents a duplicate incident.
        False otherwise.
    """

    if response is None:
        return False

    if response.status_code != 400:
        return False

    try:
        error_json = response.json()
    except ValueError:
        logger.warning(
            "PagerDuty returned HTTP 400, but the response was not valid JSON."
        )
        return False

    error = error_json.get("error", {})

    error_code = error.get("code")
    error_messages = error.get("errors", [])

    # Primary check: PagerDuty's documented/observed duplicate error code.
    if error_code == PD_DUPLICATE_ERROR_CODE:
        return True

    # Secondary check: protect against the error code changing while
    # the actual duplicate message remains the same.
    if any(
        PD_DUPLICATE_ERROR_TEXT.lower() in str(message).lower()
        for message in error_messages
    ):
        return True

    return False


# ---------------------------------------------------------------------------
# Create PagerDuty incident
# ---------------------------------------------------------------------------

def trigger_incident(
    api_key: str,
    service_id: str,
    title: str,
    description: str,
    urgency: str = "high",
    escalation_policy_id: str | None = None,
    from_email: str | None = None,
    incident_key: str | None = None,
    dedup_window_minutes: int = 24 * 60,
    timeout: float = REQUEST_TIMEOUT,
) -> dict:
    """
    Create a PagerDuty incident using the REST API.

    If PagerDuty reports that an open incident with the same
    incident_key already exists, the existing incident is looked up
    and reused instead of treating the request as a failure.

    Args:
        api_key:
            PagerDuty REST API token.

        service_id:
            PagerDuty service ID.

        title:
            Incident title.

        description:
            Detailed incident description.

        urgency:
            "high" or "low".

        escalation_policy_id:
            Optional escalation policy ID.

        from_email:
            Optional PagerDuty user email. Required in some cases when
            using an account-level API token.

        incident_key:
            Optional custom incident key.

            If omitted, a stable key is automatically generated.

        dedup_window_minutes:
            Deduplication window used when automatically generating
            the incident key.

        timeout:
            HTTP request timeout.

    Returns:
        Dictionary containing:

            success
            incident_key
            incident_url
            incident_number
            likely_duplicate
            message
    """

    # -----------------------------------------------------------------------
    # Generate incident key if one wasn't explicitly supplied.
    # -----------------------------------------------------------------------

    incident_key = incident_key or _build_dedup_key(
        title,
        dedup_window_minutes,
    )

    # -----------------------------------------------------------------------
    # Build PagerDuty incident payload.
    # -----------------------------------------------------------------------

    incident_body: dict = {
        "type": "incident",
        "title": title,
        "service": {
            "id": service_id,
            "type": "service_reference",
        },
        "urgency": urgency,
        "incident_key": incident_key,
        "body": {
            "type": "incident_body",
            "details": description,
        },
    }

    # Add escalation policy only when supplied.
    if escalation_policy_id:
        incident_body["escalation_policy"] = {
            "id": escalation_policy_id,
            "type": "escalation_policy_reference",
        }

    # -----------------------------------------------------------------------
    # HTTP headers.
    # -----------------------------------------------------------------------

    headers = {
        "Accept": "application/json",
        "Authorization": f"Token token={api_key}",
        "Content-Type": "application/json",
    }

    if from_email:
        headers["From"] = from_email

    # -----------------------------------------------------------------------
    # Send request.
    # -----------------------------------------------------------------------

    try:
        logger.info(
            "Creating PagerDuty incident: incident_key=%s, service_id=%s",
            incident_key,
            service_id,
        )

        resp = requests.post(
            PD_REST_INCIDENTS_URL,
            json={"incident": incident_body},
            headers=headers,
            timeout=timeout,
        )

        # Raises HTTPError for 4xx/5xx responses.
        resp.raise_for_status()

        # -------------------------------------------------------------------
        # Successful incident creation.
        # -------------------------------------------------------------------

        incident = resp.json().get("incident", {})

        incident_url = incident.get("html_url")
        incident_number = incident.get("incident_number")

        logger.info(
            "PagerDuty incident created successfully: #%s (%s)",
            incident_number,
            incident_url,
        )

        return {
            "success": True,
            "incident_key": incident_key,
            "incident_url": incident_url,
            "incident_number": incident_number,
            "likely_duplicate": False,
            "message": "Incident created",
        }

    # -----------------------------------------------------------------------
    # HTTP errors.
    # -----------------------------------------------------------------------

    except requests.exceptions.HTTPError as exc:

        response = exc.response

        status_code = (
            response.status_code
            if response is not None
            else None
        )

        body_text = (
            response.text
            if response is not None
            else ""
        )

        # ================================================================
        # DUPLICATE INCIDENT
        # ================================================================

        if _is_duplicate_incident_error(response):

            logger.info(
                "PagerDuty incident already exists for incident_key=%s. "
                "This is an expected duplicate response; looking up "
                "the existing incident.",
                incident_key,
            )

            existing = _lookup_incident_by_key(
                api_key=api_key,
                incident_key=incident_key,
                timeout=timeout,
            )

            if existing:

                existing_url = existing.get("html_url")
                existing_number = existing.get("incident_number")

                logger.info(
                    "Reusing existing PagerDuty incident #%s (%s) "
                    "for incident_key=%s.",
                    existing_number,
                    existing_url,
                    incident_key,
                )

                return {
                    "success": True,
                    "incident_key": incident_key,
                    "incident_url": existing_url,
                    "incident_number": existing_number,
                    "likely_duplicate": True,
                    "message": "Reused existing open incident",
                }

            # ----------------------------------------------------------------
            # PagerDuty confirmed duplicate, but lookup did not find it.
            # ----------------------------------------------------------------

            logger.warning(
                "PagerDuty confirmed that incident_key=%s already has "
                "an open incident, but the existing incident could not "
                "be retrieved.",
                incident_key,
            )

            return {
                "success": False,
                "incident_key": incident_key,
                "incident_url": None,
                "incident_number": None,
                "likely_duplicate": True,
                "message": (
                    "PagerDuty reported an existing open incident, "
                    "but the existing incident could not be retrieved. "
                    f"Response: {body_text}"
                ),
            }

        # ================================================================
        # OTHER HTTP 400 / 4XX / 5XX ERRORS
        # ================================================================

        logger.error(
            "PagerDuty REST API error: HTTP %s — %s",
            status_code,
            body_text or str(exc),
        )

        return {
            "success": False,
            "incident_key": incident_key,
            "incident_url": None,
            "incident_number": None,
            "likely_duplicate": False,
            "message": (
                f"{exc} — "
                f"{body_text or '(no response body)'}"
            ),
        }

    # -----------------------------------------------------------------------
    # Network / connection / timeout errors.
    # -----------------------------------------------------------------------

    except requests.exceptions.RequestException as exc:

        logger.error(
            "PagerDuty request failed: %s",
            exc,
        )

        return {
            "success": False,
            "incident_key": incident_key,
            "incident_url": None,
            "incident_number": None,
            "likely_duplicate": False,
            "message": str(exc),
        }


# ---------------------------------------------------------------------------
# Lookup existing incident
# ---------------------------------------------------------------------------

def _lookup_incident_by_key(
    api_key: str,
    incident_key: str,
    timeout: float,
) -> dict | None:
    """
    Find an existing PagerDuty incident using its incident key.

    Args:
        api_key:
            PagerDuty REST API token.

        incident_key:
            Incident/deduplication key.

        timeout:
            HTTP request timeout.

    Returns:
        Existing incident dictionary, or None if no matching incident
        could be found.
    """

    try:

        logger.info(
            "Looking up existing PagerDuty incident: incident_key=%s",
            incident_key,
        )

        resp = requests.get(
            PD_REST_INCIDENTS_URL,
            params={
                "incident_key": incident_key,
            },
            headers={
                "Authorization": f"Token token={api_key}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

        resp.raise_for_status()

        incidents = resp.json().get(
            "incidents",
            [],
        )

        logger.info(
            "PagerDuty lookup for incident_key=%s found %d matching incident(s).",
            incident_key,
            len(incidents),
        )

        return incidents[0] if incidents else None

    except requests.exceptions.RequestException as exc:

        logger.error(
            "Failed to look up existing PagerDuty incident "
            "for incident_key=%s: %s",
            incident_key,
            exc,
        )

        return None


# ---------------------------------------------------------------------------
# Resolve PagerDuty incident
# ---------------------------------------------------------------------------

def resolve_incident(
    routing_key: str,
    dedup_key: str,
) -> dict:
    """
    Resolve an existing PagerDuty incident using the Events API v2.

    Args:
        routing_key:
            PagerDuty Events API v2 integration/routing key.

        dedup_key:
            Deduplication key of the incident to resolve.

    Returns:
        Dictionary containing success status and message.
    """

    payload = {
        "routing_key": routing_key,
        "event_action": "resolve",
        "dedup_key": dedup_key,
    }

    try:

        resp = requests.post(
            PD_EVENTS_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
            },
            timeout=REQUEST_TIMEOUT,
        )

        resp.raise_for_status()

        logger.info(
            "PagerDuty incident resolved successfully. dedup_key=%s",
            dedup_key,
        )

        return {
            "success": True,
            "message": "Incident resolved",
        }

    except requests.exceptions.RequestException as exc:

        logger.error(
            "Failed to resolve PagerDuty incident: %s",
            exc,
        )

        return {
            "success": False,
            "message": str(exc),
        }