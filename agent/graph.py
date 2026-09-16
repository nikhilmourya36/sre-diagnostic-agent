"""
The LangGraph diagnostic agent.

Replaces slack_listener.py's previous fixed sequence (always: ack -> SOP
lookup -> static checklist) with an actual reasoning agent that decides
which tools to call, correlates their results, and writes a synthesized
conclusion -- per CLAUDE.md's core design principle: the agent never
decides the final verdict alone, every claim traces back to a real tool
result, but the CORRELATION and explanation is genuinely the agent's job,
not a fixed template.

Tools wired in (all 3 from CLAUDE.md's initial build order):
  - check_site_health  (agent/tools/sanity_checker.py, reused as-is)
  - check_k8s_workload (agent/tools/check_k8s_workload.py)
  - retrieve_sop       (agent/tools/retrieve_sop.py)

check_recent_releases, check_logs, check_grafana_metric are NOT wired in
yet -- per CLAUDE.md, add those only after this smaller set is proven
working end-to-end.
"""
from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from config.settings import GROQ_API_KEY, GROQ_MODEL
from agent.tools.check_k8s_workload import check_k8s_workload as _check_k8s_workload
from agent.tools.retrieve_sop import retrieve_sop as _retrieve_sop
from agent.tools.sanity_checker import run_sanity_check as _run_sanity_check

# The URL the sanity checker points at -- the demo backend's public/
# in-cluster address. For now this is the only site the agent checks;
# CLAUDE.md's MONITORED_URLS-style multi-service support isn't needed
# yet since there's only one target service in this project.
_DEMO_BACKEND_URL = "http://localhost:8080"  # matches the port-forward
# convention used throughout this project's manual testing. If the
# agent ever runs somewhere that can reach the cluster directly (e.g.
# via a Service DNS name from inside the cluster), update this --
# currently assumes a port-forward is active, same as every manual test
# so far in this project.


@tool
def check_site_health() -> dict:
    """Run a real DNS/HTTP/latency/SSL check against the demo backend
    service to confirm whether it's actually down or degraded, rather
    than assuming based on the alert text alone."""
    report = _run_sanity_check(_DEMO_BACKEND_URL)
    return report.to_dict()


@tool
def check_k8s_workload(deployment_name: str = "demo-backend", namespace: str = "default") -> dict:
    """Check a Kubernetes Deployment's pod health: status, restart counts,
    and recent events. Use this to confirm whether pod crashes or restarts
    explain the reported symptoms. Defaults to the demo-backend deployment
    in the default namespace, which is this project's only current
    target service."""
    return _check_k8s_workload(deployment_name, namespace)


@tool
def retrieve_sop(query: str) -> dict:
    """Search the SOP knowledge base (synced from Confluence) for
    documentation relevant to the incident. Returns up to 3 candidate
    SOPs -- more than one may be genuinely relevant, so weigh them
    against what the other tools actually found rather than assuming
    the top result is automatically correct."""
    return _retrieve_sop(query)


_SYSTEM_PROMPT = """You are an SRE diagnostic assistant. An incident alert has just fired.

Your job: investigate using the tools available, then write ONE clear,
short conclusion for the on-call engineer -- not a dump of raw tool output.

Rules:
- ALWAYS call check_site_health AND check_k8s_workload before concluding
  anything -- never guess whether the service is actually down or pods
  are actually unhealthy without checking.
- ALWAYS call retrieve_sop with a query describing the symptoms, so you
  can point to a specific relevant runbook.
- If retrieve_sop returns multiple candidate SOPs, reason about which
  ones actually fit what check_site_health and check_k8s_workload found
  -- don't just pick the first result blindly.
- CORRELATE, don't just list. If pod restarts are recent AND the site
  check shows errors, say so explicitly -- that's a much stronger signal
  than either fact alone. If nothing found by the tools points to
  Kubernetes issues, don't mention pod restarts just because you checked.
- Be honest about uncertainty. If the tools don't clearly point to a
  cause, say what you found and what to check next -- don't invent a
  confident-sounding root cause the evidence doesn't support.
- End with a short, concrete "where to start looking" pointer for the
  on-call engineer -- one or two sentences, not a restated checklist.
- Keep the whole reply under ~150 words. This posts directly into a
  Slack thread -- on-call needs a fast, scannable answer, not a report.
- Include the SOP link(s) you used, formatted as Slack markdown:
  <url|Title>
"""

_agent = None  # lazy singleton -- avoid reinitializing the LLM client on every call


def get_agent():
    global _agent
    if _agent is not None:
        return _agent

    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set -- fill it in .env before running the agent."
        )

    llm = ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0)
    _agent = create_agent(
        llm,
        tools=[check_site_health, check_k8s_workload, retrieve_sop],
        system_prompt=_SYSTEM_PROMPT,
    )
    return _agent


def diagnose(alert_text: str) -> str:
    """
    Run the full agent loop against an incident's alert text (e.g. the
    text PagerDuty posted into Slack). Returns the agent's final
    synthesized reply, ready to post back into the Slack thread.
    """
    agent = get_agent()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"Incident alert: {alert_text}"}]}
    )
    final_message = result["messages"][-1]
    return final_message.content


if __name__ == "__main__":
    # Manual test -- run this directly (from the project root, so
    # imports resolve) to see the agent's reasoning against a real
    # incident description, without needing Slack in the loop at all.
    test_alert = "Triggered: Incident on Web-Frontend-Team — 5xx count high | major_default | High urgency."
    print(f"Testing agent with alert: {test_alert!r}\n")
    print(diagnose(test_alert))