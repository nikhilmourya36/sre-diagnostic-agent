# Grafana Diagnostic Agent

The sequel to [`slack-pagerduty-incident-bot`](../slack-pagerduty-incident-bot3) —
see `CLAUDE.md` for the full project vision. This README covers what's
actually in this repo and how the pieces fit together.

**Full context, architecture, and design decisions live in [`CLAUDE.md`](./CLAUDE.md).
Read that first if you're new here.**

---

## What's reused from the previous project, and what's new

This is **not** a merge of the two repos — it's a new project that borrows
proven pieces where they genuinely fit, because the reasoning shape
(multi-tool LangGraph agent vs. classify-then-single-tool) is different
enough that porting the old bot's agent logic wholesale would create more
confusion than starting clean.

The trigger mechanism itself, though, turned out to be closer to the old
project than originally planned — see the "trigger redesign" note below.

| Component | Status | Source |
|---|---|---|
| `agent/tools/sanity_checker.py` | Reused as-is | Copied from the old repo's `tools/sanity_checker.py` |
| `agent/pagerduty_client.py` | Reused as-is | Copied from the old repo's `bot/pagerduty_client.py` — still fires in parallel, untouched |
| `config/` pattern | Reused as a *pattern*, new file | Old repo's "one settings file, no scattered `os.getenv`" approach, applied to this project's own variables (EKS, Confluence, Grafana) |
| Slack posting + listener (Bolt, Socket Mode, reply-in-thread) | Reused as a *pattern and largely as code* | See trigger redesign below — this project's trigger turned out to be a Slack message too, just from Alertmanager instead of a human |
| Agent/classification logic | New | The old `bot/llm_agent.py` does classify-then-single-tool; this project needs a LangGraph multi-tool agent — different enough to build fresh |
| `tools/product_search.py` | Not used | Not relevant to this project's scenarios |

### Trigger redesign: no inbound webhook after all

Originally planned as Grafana pushing a webhook directly to an HTTP
listener on the agent's VM. Revised once we settled on running the agent
in **Colab** for demo purposes (reusing the same environment as the prior
project) — Colab has no public inbound URL by default, so there was
nowhere for a webhook to land without standing up a tunnel (ngrok/similar)
just for this.

Instead: **Alertmanager posts into a dedicated alerts-only Slack channel**,
and the agent's Slack bot (same Socket Mode, outbound-only pattern as the
old project) watches that channel instead of an HTTP port. PagerDuty is
also configured to post into Slack directly, in parallel — so the incident
notification and the agent's diagnosis both land in the same place,
without the agent gating or depending on PagerDuty at all.

This means the planned `webhook/` FastAPI receiver is no longer part of
this project — full reasoning in `CLAUDE.md`'s Trigger section.

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
│                                    #   (next: Alertmanager -> Slack receiver config,
│                                    #    not yet documented here)
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
├── agent/                        # STEP 2-3 — Slack listener + LangGraph agent
│   ├── pagerduty_client.py        # Reused from the old project, as-is
│   ├── tools/
│   │   └── sanity_checker.py      # Reused from the old project, as-is
│   │   # (not yet added: check_k8s_workload, check_logs,
│   │   #  check_grafana_metric, check_recent_releases, retrieve_sop)
│   ├── (Slack listener — not yet built, watches the dedicated alerts
│   │   channel, same Socket Mode pattern as the old project's
│   │   bot/slack_handler.py, different trigger logic)
│   └── (agent graph / LangGraph wiring — not built yet)
│
└── config/                       # Project-wide settings (not built yet)
    └── (settings.py — EKS, Confluence, Grafana config, one place, pattern
        borrowed from the old project's config/settings.py)
```

Note: there is no `webhook/` folder — see the trigger redesign above.

---

## Build order

This matches `CLAUDE.md`'s build order exactly — infra first, then
alerting, then the agent, then integration with Slack/PagerDuty last:

1. **`infra/`** — stand up the EKS cluster + demo backend, confirm the
   break-switch endpoints work. *(in progress)*
2. **`infra/observability/`** — install Prometheus + Grafana, wire
   scraping, add one alert rule, prove it fires and resolves against a
   real triggered failure. *(in progress)*
3. **Alertmanager → dedicated Slack channel** (plain notification, human
   still the only responder), plus PagerDuty's own Slack integration
   configured in parallel — proves the alerting pipeline end-to-end before
   any agent code exists. *(not started — see CLAUDE.md step 0.75)*
4. **`sync/`** — finish the Confluence sync + chunker + embed into a
   vector DB. Independent of the infra steps above, can happen in
   parallel. *(in progress — connection test + structure survey done,
   chunker not yet built)*
5. **`agent/` Slack listener** — watches the dedicated alerts channel,
   confirms it can receive and parse a real Alertmanager-posted alert
   message. Same Socket Mode pattern as the old project, no inbound HTTP
   needed. *(not started)*
6. **`agent/` LangGraph wiring** — starting with just 3 tools
   (`check_site_health` — reused — `check_k8s_workload`, `retrieve_sop`)
   before adding the rest. *(not started — the two reused files are in
   place as a head start)*
7. **Integration**: agent posts its diagnosis back in the same Slack
   thread, PagerDuty continues to fire in parallel and post to Slack
   directly, untouched by the agent. *(last step, not first — this
   project is only "integrated" with the old one at this final stage, not
   from day one)*

---

## Why infra comes before any agent/integration code

Per `CLAUDE.md`: the target system (EKS + services) didn't exist yet when
this project started, so there's nothing to diagnose until it's real. Each
step above is meant to be provably working on its own — a real alert
firing in Prometheus's UI, a real Slack message from Alertmanager — before
the next layer is built on top of it. This avoids debugging "is my agent
wrong or is my alerting wrong" simultaneously with both pieces being new.
