"""
Sanity Checker
==============
Runs a lightweight external health check against a URL:
  - DNS resolution
  - HTTP status code
  - Response latency
  - SSL certificate validity (https only)

Produces an overall status:
  GREEN  — everything looks healthy
  YELLOW — reachable but degraded (slow, or SSL nearing/failing softly)
  RED    — unreachable or clearly down (DNS failure, connection error,
           timeout, or 5xx server error)

REUSE NOTE: copied as-is from the slack-pagerduty-incident-bot3 project
(tools/sanity_checker.py). No changes made yet. Point this at the
infra/app demo backend's URL once it's deployed — this becomes the
`check_site_health` tool in the LangGraph agent (see CLAUDE.md).
"""
from __future__ import annotations

import socket
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

DEFAULT_TIMEOUT = 10.0
DEFAULT_LATENCY_THRESHOLD = 3.0


@dataclass
class Check:
    name: str
    passed: bool
    message: str
    value: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "value": self.value,
        }


@dataclass
class SanityReport:
    url: str
    status: str  # GREEN | YELLOW | RED
    checks: list[Check] = field(default_factory=list)
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "status": self.status,
            "checked_at": self.checked_at,
            "checks": [c.to_dict() for c in self.checks],
        }


def run_sanity_check(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    latency_threshold: float = DEFAULT_LATENCY_THRESHOLD,
) -> SanityReport:
    """Run DNS, HTTP, latency, and SSL checks against *url*."""
    checks: list[Check] = []
    parsed = urlparse(url)
    hostname = parsed.hostname or url

    # 1. DNS resolution
    dns_ok, dns_check = _check_dns(hostname)
    checks.append(dns_check)

    if not dns_ok:
        # No point checking HTTP/SSL if DNS itself fails.
        return SanityReport(url=url, status="RED", checks=checks)

    # 2. HTTP status + latency
    http_ok, is_server_error, latency, http_check, latency_check = _check_http(
        url, timeout, latency_threshold
    )
    checks.append(http_check)
    checks.append(latency_check)

    # 3. SSL certificate (only for https)
    ssl_ok = True
    if parsed.scheme == "https":
        ssl_ok, ssl_check = _check_ssl(hostname, parsed.port or 443, timeout)
        checks.append(ssl_check)

    # ------------------------------------------------------------------
    # Decide overall status
    # ------------------------------------------------------------------
    if not http_ok or is_server_error:
        status = "RED"
    elif latency is not None and latency > latency_threshold:
        status = "YELLOW"
    elif not ssl_ok:
        status = "YELLOW"
    else:
        status = "GREEN"

    return SanityReport(url=url, status=status, checks=checks)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_dns(hostname: str) -> tuple[bool, Check]:
    try:
        ip = socket.gethostbyname(hostname)
        return True, Check(
            name="DNS Resolution",
            passed=True,
            message=f"Resolved to {ip}",
            value=ip,
        )
    except socket.gaierror as exc:
        return False, Check(
            name="DNS Resolution",
            passed=False,
            message=f"Failed to resolve hostname: {exc}",
        )


def _check_http(
    url: str, timeout: float, latency_threshold: float
) -> tuple[bool, bool, float | None, Check, Check]:
    start = time.monotonic()
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        latency = round(time.monotonic() - start, 2)

        is_server_error = resp.status_code >= 500
        http_ok = resp.status_code < 500  # 4xx = reachable but client-side issue

        http_check = Check(
            name="HTTP Status",
            passed=resp.status_code < 400,
            message=f"HTTP {resp.status_code}",
            value=str(resp.status_code),
        )
        latency_check = Check(
            name="Response Time",
            passed=latency <= latency_threshold,
            message=f"Responded in {latency}s (threshold {latency_threshold}s)",
            value=f"{latency}s",
        )
        return http_ok, is_server_error, latency, http_check, latency_check

    except requests.exceptions.Timeout:
        latency = round(time.monotonic() - start, 2)
        http_check = Check(
            name="HTTP Status", passed=False, message=f"Timed out after {timeout}s"
        )
        latency_check = Check(
            name="Response Time", passed=False, message="Timed out", value=None
        )
        return False, False, latency, http_check, latency_check

    except requests.exceptions.RequestException as exc:
        http_check = Check(
            name="HTTP Status", passed=False, message=f"Request failed: {exc}"
        )
        latency_check = Check(
            name="Response Time", passed=False, message="N/A — request failed"
        )
        return False, False, None, http_check, latency_check


def _check_ssl(hostname: str, port: int, timeout: float) -> tuple[bool, Check]:
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()

        not_after = cert.get("notAfter") if cert else None
        expiry_note = f", expires {not_after}" if not_after else ""
        return True, Check(
            name="SSL Certificate",
            passed=True,
            message=f"Valid{expiry_note}",
            value=not_after,
        )
    except ssl.SSLError as exc:
        return False, Check(
            name="SSL Certificate", passed=False, message=f"SSL error: {exc}"
        )
    except (socket.timeout, OSError) as exc:
        return False, Check(
            name="SSL Certificate", passed=False, message=f"Could not verify: {exc}"
        )
