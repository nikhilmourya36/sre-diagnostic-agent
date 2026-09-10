# Grafana Diagnostic Agent

The sequel to [`slack-pagerduty-incident-bot`](../slack-pagerduty-incident-bot3) —
see `CLAUDE.md` for the full project vision. This README covers what's
actually in this repo and how the pieces fit together.

**Full context, architecture, and design decisions live in [`CLAUDE.md`](./CLAUDE.md).
Read that first if you're new here.**

---

## What's reused from the previous project, and what's new

This is **not** a merge of the two repos — it's a new project that borrows
two proven files and one pattern, because the trigger (Grafana webhook vs.
a human typing in Slack) and the reasoning shape (multi-tool LangGraph
agent vs. classify-then-single-tool) are different enough that porting the
old bot logic wholesale would create more confusion than starting clean.

| Component | Status | Source |
|---|---|---|
| `agent/tools/sanity_checker.py` | Reused as-is | Copied from the old repo's `tools/sanity_checker.py` |
| `agent/pagerduty_client.py` | Reused as-is | Copied from the old repo's `bot/pagerduty_client.py` — still fires in parallel, untouched |
| `config/` pattern | Reused as a *pattern*, new file | Old repo's "one settings file, no scattered `os.getenv`" approach, applied to this project's own variables (EKS, Confluence, Grafana) |
| Slack posting (Bolt, reply-in-thread) | Reused as a *pattern*, new code | The "how to post in Slack" approach carries over; the event-listener logic doesn't, since this project's trigger is a webhook, not a Slack message |
| Agent/classification logic | New | The old `bot/llm_agent.py` does classify-then-single-tool; this project needs a LangGraph multi-tool agent — different enough to build fresh |
| `tools/product_search.py` | Not used | Not relevant to this project's scenarios |

---

## Directory structure

```
.
├── CLAUDE.md                    # Full project context — read this first
├── README.md                    # This file
│
├── infra/                       # STEP 0 — the target system (build first)
│   ├── terraform/                # Minimal EKS cluster
│   ├── app/                      # Demo backend service (Flask) + Dockerfile
│   │                              #   has /break/5xx and /break/crash endpoints
│   │                              #   for triggering real, on-demand failures
│   └── k8s/                      # Deployment/Service manifests
│
├── infra/observability/          # STEP 0.5 — Prometheus + Grafana (build second)
│   ├── values.yaml                # kube-prometheus-stack Helm values
│   ├── service-monitor.yaml       # Tells Prometheus to scrape the demo backend
│   ├── alert-rule.yaml            # The one alert rule to start with
│   └── README.md                  # Install steps + how to prove the alert fires
│
├── sops/                         # SOP source content (in progress)
│   └── *.md                       # 11 draft SOPs — copy these into Confluence
│                                    #   with real heading structure
│
├── sync/                         # Confluence -> vector DB sync (in progress)
│   ├── 00_test_connection.py      # Step 1 — prove Confluence API access works
│   └── 01_survey_structure.py     # Step 2 — check heading structure across pages
│                                    #   (next: 02_chunk_and_embed.py, not built yet)
│
├── webhook/                      # STEP 2 — Grafana alert receiver (not built yet)
│   └── (FastAPI app that receives Alertmanager webhooks, hands off to agent/)
│
├── agent/                        # STEP 3 — the LangGraph agent (not built yet)
│   ├── pagerduty_client.py        # Reused from the old project, as-is
│   ├── tools/
│   │   └── sanity_checker.py      # Reused from the old project, as-is
│   │   # (not yet added: check_k8s_workload, check_logs,
│   │   #  check_grafana_metric, check_recent_releases, retrieve_sop)
│   └── (agent graph / LangGraph wiring — not built yet)
│
└── config/                       # Project-wide settings (not built yet)
    └── (settings.py — EKS, Confluence, Grafana config, one place, pattern
        borrowed from the old project's config/settings.py)
```

---

## Build order

This matches `CLAUDE.md`'s build order exactly — infra first, then
alerting, then the agent, then integration with Slack/PagerDuty last:

1. **`infra/`** — stand up the EKS cluster + demo backend, confirm the
   break-switch endpoints work. *(in progress)*
2. **`infra/observability/`** — install Prometheus + Grafana, wire
   scraping, add one alert rule, prove it fires and resolves against a
   real triggered failure. *(in progress)*
3. **Alertmanager → Slack directly** (plain notification, human still the
   only responder) — proves the alerting pipeline end-to-end before any
   agent code exists. *(not started — see CLAUDE.md step 0.75)*
4. **`sync/`** — finish the Confluence sync + chunker + embed into a
   vector DB. Independent of the infra steps above, can happen in
   parallel. *(in progress — connection test + structure survey done,
   chunker not yet built)*
5. **`webhook/`** — small FastAPI app that receives the Grafana/
   Alertmanager webhook payload. *(not started)*
6. **`agent/`** — wire the LangGraph agent with the tool set from
   `CLAUDE.md`, starting with just 3 tools (`check_site_health` —
   reused — `check_k8s_workload`, `retrieve_sop`) before adding the rest.
   *(not started — the two reused files are in place as a head start)*
7. **Integration**: agent posts to Slack (same channel/pattern as the old
   bot), PagerDuty continues to fire in parallel via Alertmanager
   directly, untouched. *(last step, not first — this project is only
   "integrated" with the old one at this final stage, not from day one)*

---

## Why infra comes before any agent/integration code

Per `CLAUDE.md`: the target system (EKS + services) didn't exist yet when
this project started, so there's nothing to diagnose until it's real. Each
step above is meant to be provably working on its own — a real alert
firing in Prometheus's UI, a real Slack message from Alertmanager — before
the next layer is built on top of it. This avoids debugging "is my agent
wrong or is my alerting wrong" simultaneously with both pieces being new.
