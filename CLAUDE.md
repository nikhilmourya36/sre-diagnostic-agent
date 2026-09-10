# CLAUDE.md

This file gives context on what this project is and where it's headed. Read
this before making structural changes or adding new tools/integrations.

---

## What this project is

An AI agent that turns a Grafana alert into an actual diagnosis, not just a
notification.

Today, when something breaks (e.g. a 5xx spike on the homepage), Grafana
fires an alert, on-call gets pinged, and then a human has to manually go
check five different places — the service itself, Kubernetes, logs, other
Grafana panels, the release history, and whatever SOP might exist for this
exact situation — before they even know where to start looking.

This project automates that first-response investigation. The moment
Grafana fires, an agent running on our VM:

### Infrastructure scope — being built from scratch, together

This is not being retrofitted onto existing infrastructure. Both sides are
being built as part of this project:

- **The target system**: a new AWS EKS cluster, with a frontend and
  backend service deployed on it. This is what will actually break/fail
  and get monitored — it doesn't exist yet.
- **Also being built from scratch**: Prometheus + Grafana, installed onto
  the new EKS cluster via the `kube-prometheus-stack` Helm chart. Nothing
  here was pre-existing — metrics, scraping, alert rules, and Alertmanager
  are all new as of this project.
- **Already in place**: PagerDuty and Slack are already set up from prior
  work and get reused as-is, not rebuilt (this is what the earlier
  `slack-pagerduty-incident-bot3` project already integrates with).
- **The agent**: runs separately from the EKS cluster (a VM, or
  potentially a different cluster) — it does not run inside the cluster
  it's monitoring. It connects INTO EKS as one of its checks (via the
  Kubernetes API), the same way it connects into Grafana, Confluence, etc.
  Keeping the agent outside the monitored cluster is deliberate: if EKS
  itself is having a bad day, we don't want the thing diagnosing it to be
  affected by the same outage.

Because the target infra doesn't exist yet, we get to shape it
deliberately — e.g. instrumenting the frontend/backend with the specific
failure modes we want the agent to be good at diagnosing (5xx spikes, pod
restarts, FD leaks) rather than discovering after the fact what's hard to
observe.

1. Runs a real sanity check against the affected service
2. Checks the relevant Kubernetes workload for restarts/crashes
3. Checks recent logs for error spikes
4. Pulls the specific Grafana metric that might explain it (e.g. open file
   descriptor count)
5. Looks up whether we already have a documented SOP for this exact
   situation (from Confluence)
6. Checks whether a recent release (last ~24h) to the affected service
   might be the cause
7. Posts one message in Slack with a synthesized conclusion — not a wall of
   raw tool output, but "start looking here, because X + Y + Z line up" —
   citing exactly which check or SOP pointed there

PagerDuty paging continues to happen in parallel, exactly as it already
does today — this project does not touch or replace that path. This is
purely about giving the on-call engineer a head start the moment they open
the incident, instead of starting from zero.

### Relationship to the existing Slack incident bot

This is the natural sequel to our existing `slack-pagerduty-incident-bot`
project. That bot is reactive to **humans** — someone types "is the site
down?" in Slack, the bot classifies it and runs one check. This project is
reactive to **Grafana** — no human has to type anything, and the agent runs
a full multi-tool investigation instead of a single check.

We reuse what already works from that project rather than rebuilding it:
- The sanity-check tool (DNS/HTTP/latency/SSL) carries over largely as-is
- The PagerDuty client carries over as-is (it still runs in parallel, just
  not through the agent)
- The Slack posting pattern (Bolt, Socket Mode, reply-in-thread) carries
  over as-is

What's new here: the trigger is a Grafana webhook instead of a Slack
message, the tool belt grows from 2 tools to 6, and there's a real RAG
pipeline (Confluence-backed) instead of no retrieval at all.

---

## Core design principle (carried over from the last project)

The agent never gets to just assert a conclusion from its own reasoning
alone — every claim in its final Slack message has to trace back to a real
tool result: a live check that actually ran, a Confluence page that
actually exists, or a release that actually happened in the last 24h. The
agent's job is to run the right tools, correlate what they found, and
explain it clearly — not to guess.

Concretely: the final message should let someone verify every sentence by
clicking through to the source (the Confluence page link, the specific pod
name, the specific release/PR link) — not just take the agent's word for
it.

---

## How we're going to build this

### Trigger: Grafana → our agent

Grafana contact points support arbitrary webhooks. We run a small HTTP
listener (FastAPI) on the VM that receives the alert payload directly from
Grafana — no polling. The payload includes the alert name, labels (e.g.
`service=homepage`), and the current metric values, which becomes the
starting context for the agent.

### Agent: LangGraph, tool-calling

We use LangGraph's `create_react_agent` (same pattern explored for the
prior project) with a system prompt that pushes it toward **correlated
reasoning**, not a flat list of findings — e.g. explicitly reason about
whether the timing of a recent release lines up with when the symptoms
started, rather than just reporting "there was a release" and "there are
restarts" as two disconnected facts.

### Tools

| Tool | Backing system | Notes |
|---|---|---|
| `check_site_health` | Reused sanity checker | DNS / HTTP / latency / SSL |
| `check_k8s_workload` | Kubernetes API (`kubernetes` python client) | Restart counts, pod status, recent events for the affected deployment |
| `check_logs` | Wherever our logs live (Loki if available, else `kubectl logs` grep) | Error rate/spike in the recent window |
| `check_grafana_metric` | Grafana query API | Pulls a specific panel's data (e.g. open FD count) when the SOP or reasoning calls for it |
| `retrieve_sop` | Our own vector DB, synced from Confluence | See RAG section below — never queries Confluence live |
| `check_recent_releases` | Release/deploy source (Slack `#releases` channel history, or GitHub Releases/Deployments API) | Filtered to last 24h, filtered to the affected service where possible |

### RAG: Confluence-backed SOP lookup

We decided on **Confluence only** (not Coda) to keep scope tight, and on
**pre-indexing into our own vector store** rather than querying Confluence
live at alert-time — an incident is the wrong moment to add a dependency on
a third-party API being fast and available.

This is two separate loops:

**1. Sync loop (scheduled, independent of any incident)**
- Pull pages via the Confluence REST API (`content/search` with a CQL
  query, scoped to the SOP space/label — not org-wide)
- Chunk **by heading/section, not by fixed character count** — an SOP's
  value is in its ordered steps, so a chunk boundary that splits "step 2"
  from "step 3" is actively harmful, not just imprecise
- Embed each chunk and store it alongside: page title, page URL, the
  section heading it came from, and Confluence's last-modified timestamp
- Only re-embed pages whose Confluence version changed since our last
  sync, so re-syncing is cheap
- Runs on a schedule (e.g. every few hours via a cron/systemd timer) — not
  real-time. A manually-triggered re-sync is a reasonable future addition,
  not part of the first version.

**2. Retrieval loop (runtime, during an incident)**
- The `retrieve_sop` tool does a similarity search against our own vector
  DB only — it never calls Confluence directly at runtime
- Returns top-matching chunks with their source page URL, so the final
  Slack message can link straight to the SOP instead of just paraphrasing
  it

Known limitation, intentional for now: if someone edits a Confluence SOP
mid-incident, the agent won't see that update until the next scheduled
sync. Acceptable tradeoff for a first version; worth stating plainly
rather than implying real-time freshness.

### Vector DB

Chroma or Qdrant, run locally/embedded on the VM — no managed vector DB
service. Keeps the project self-contained and avoids an external dependency
for something that doesn't need to scale beyond one team's SOP corpus.

### Output: Slack

Same posting pattern as the existing bot — Bolt, Socket Mode, reply in
the relevant channel/thread. The message should read like a senior
engineer's first-response note: a short conclusion up top, then the
evidence that supports it (which check, which SOP section, which release),
each with a link back to its source.

---

## Build order (avoid wiring everything before the core loop works)

Since the target infra (EKS + services) doesn't exist yet either, the
build order starts even earlier than the tool-by-tool plan below implies:

0. **Stand up the target system first, deliberately simple.**
   A minimal EKS cluster with a backend service (frontend comes later).
   We need a real, reliable way to *cause* a 5xx spike or a pod crash on
   demand — the backend ships with `/break/5xx/on` and `/break/crash`
   endpoints for exactly this — so later steps can be tested against a
   real trigger instead of imagined ones. (`infra/` folder, in progress.)

0.5. **Install Prometheus + Grafana on the new cluster, from scratch.**
   Via `kube-prometheus-stack` (Helm). Wire up scraping for the demo
   backend, add one real alert rule, and prove it fires and resolves
   against the break-switch endpoints above BEFORE connecting it to
   Alertmanager/Slack/the agent. (`infra/observability/`, in progress.)

0.75. **Wire Alertmanager to Slack directly, still no agent involved.**
   Confirm a real Prometheus alert reaches Slack as a plain notification,
   with a human as the only responder — this proves the alerting pipeline
   end-to-end before any agent code exists.

1. Confluence sync job, standalone — this has no dependency on EKS/Grafana
   and can be finished independently (already in progress)

2. Grafana webhook receiver — confirm we can receive and parse a real
   alert payload from the real Grafana instance, once step 0's alerting is
   confirmed working

3. Three tools only to start: `check_site_health`, `check_k8s_workload`,
   `retrieve_sop` — get the agent loop working end-to-end against the real
   EKS cluster with a small, provable tool set before adding more

4. Synthesis + Slack reply, including source citations

5. Only after the above is solid: add `check_logs`, `check_grafana_metric`,
   `check_recent_releases`

PagerDuty paging is untouched throughout — it continues to fire in
parallel from Grafana's existing contact point, independent of this
project.

Note: PagerDuty and Slack are already configured from prior work and
don't need to be set up from scratch — Grafana/Prometheus and the EKS
cluster are all new and need to be built as part of steps 0-2 above.

---

## Explicitly out of scope for now

- Coda integration (Confluence only)
- Real-time Confluence sync (scheduled sync is enough)
- Any automated remediation/rollback — this project diagnoses and informs,
  it does not take corrective action on its own
- Replacing or modifying the existing PagerDuty paging path
