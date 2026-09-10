"""
Minimal backend service — the TARGET the diagnostic agent will monitor.

This is intentionally simple. Its whole purpose is to be a realistic thing
that can break in controlled, on-demand ways, so the agent (built later)
has something real to diagnose instead of a simulated/imagined incident.

Endpoints:
    GET  /             - normal healthy response
    GET  /healthz      - liveness probe target
    GET  /metrics       - Prometheus-format metrics for Grafana to scrape
    POST /break/5xx/on  - start returning 500s on every request to "/"
    POST /break/5xx/off - stop returning 500s, back to healthy
    POST /break/crash   - exit the process immediately (simulates a crash,
                           triggers a pod restart)

The /break/* endpoints exist ONLY to let you test the alerting and agent
pipeline on demand. They are not authenticated — do not expose this
service outside a private/demo environment.
"""
from __future__ import annotations

import os
import random
import sys
import time

from flask import Flask, Response

app = Flask(__name__)

START_TIME = time.time()
REQUEST_COUNT = 0
ERROR_COUNT = 0

# Toggled by /break/5xx/on and /break/5xx/off — this is the "incident
# switch" you flip to test the whole pipeline end to end.
_FORCE_5XX = False


@app.route("/")
def home():
    global REQUEST_COUNT, ERROR_COUNT
    REQUEST_COUNT += 1

    if _FORCE_5XX:
        ERROR_COUNT += 1
        return Response("Internal Server Error (forced for testing)", status=500)

    return {"status": "ok", "service": "demo-backend"}


@app.route("/healthz")
def healthz():
    # Deliberately NOT affected by the 5xx toggle — this is the liveness
    # probe. If you want to test a pod actually restarting due to failed
    # health checks, use /break/crash instead, not this endpoint.
    return {"status": "healthy"}


@app.route("/metrics")
def metrics():
    """
    Bare-bones Prometheus exposition format. Enough for Grafana to have
    something real to alert on (request count, error count, error rate).
    Extend this later if the agent needs richer signals (latency
    histogram, open file descriptors, etc.) — don't over-build it now.
    """
    uptime = time.time() - START_TIME
    error_rate = (ERROR_COUNT / REQUEST_COUNT) if REQUEST_COUNT else 0.0

    body = (
        f"# HELP demo_backend_uptime_seconds Time since process start\n"
        f"# TYPE demo_backend_uptime_seconds gauge\n"
        f"demo_backend_uptime_seconds {uptime}\n"
        f"# HELP demo_backend_requests_total Total requests served\n"
        f"# TYPE demo_backend_requests_total counter\n"
        f"demo_backend_requests_total {REQUEST_COUNT}\n"
        f"# HELP demo_backend_errors_total Total 5xx responses served\n"
        f"# TYPE demo_backend_errors_total counter\n"
        f"demo_backend_errors_total {ERROR_COUNT}\n"
        f"# HELP demo_backend_error_rate Fraction of requests that were 5xx\n"
        f"# TYPE demo_backend_error_rate gauge\n"
        f"demo_backend_error_rate {error_rate}\n"
    )
    return Response(body, mimetype="text/plain")


@app.route("/break/5xx/on", methods=["POST"])
def break_5xx_on():
    global _FORCE_5XX
    _FORCE_5XX = True
    return {"status": "5xx mode ON — / will now return 500"}


@app.route("/break/5xx/off", methods=["POST"])
def break_5xx_off():
    global _FORCE_5XX
    _FORCE_5XX = False
    return {"status": "5xx mode OFF — / back to healthy"}


@app.route("/break/crash", methods=["POST"])
def break_crash():
    # Exits immediately. Under Kubernetes, this causes the pod to
    # terminate and restart — use this to test pod-restart / crash-loop
    # detection in the agent later.
    sys.exit(1)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
