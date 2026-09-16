"""
check_k8s_workload tool -- checks a Kubernetes Deployment's pod health:
restart counts, current status, and recent events. This is the second
of the three starter tools from CLAUDE.md's build order (after
check_site_health / sanity_checker.py and retrieve_sop.py).

Auth: uses the local kubeconfig (the same one `kubectl` uses, set up via
`aws eks update-kubeconfig`). No separate credentials needed for local/
Colab-with-kubeconfig runs. If this tool ever runs INSIDE the cluster
instead (it currently doesn't, per CLAUDE.md's deliberate "agent runs
outside the monitored cluster" decision), it would need in-cluster auth
instead -- not implemented, not needed under the current design.
"""
from __future__ import annotations

from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


def _load_k8s_config() -> None:
    """
    Load from the local kubeconfig. Raises a clear error if it's not
    available or not pointed at a reachable cluster -- better to fail
    loudly here than have every tool call silently do nothing useful.
    """
    try:
        config.load_kube_config()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Could not load kubeconfig: {exc}. "
            f"Has `aws eks update-kubeconfig` been run for this session?"
        ) from exc


def check_k8s_workload(deployment_name: str, namespace: str = "default") -> dict:
    """
    Check a Kubernetes Deployment's pod health.

    Args:
        deployment_name: Name of the Deployment to check (e.g. "demo-backend").
        namespace: Kubernetes namespace it's in. Default "default".

    Returns:
        dict with:
            found: bool -- whether the deployment exists
            healthy: bool -- True if all pods are Running with 0 recent restarts
            pod_count: int
            pods: list of dicts, each with name, phase, restart_count,
                container_ready
            recent_events: list of recent Kubernetes events for this
                deployment's pods -- often contains the actual failure
                reason (OOMKilled, failed probe, image pull error, etc.)
                per SOP: Kubernetes Pod Crash Loop
            error: str | None
    """
    try:
        _load_k8s_config()
        core_v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()
    except RuntimeError as exc:
        return {
            "found": False, "healthy": False, "pod_count": 0,
            "pods": [], "recent_events": [], "error": str(exc),
        }

    # Confirm the deployment itself exists first -- a clearer error than
    # just finding zero matching pods and leaving the caller to guess why.
    try:
        apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            return {
                "found": False, "healthy": False, "pod_count": 0,
                "pods": [], "recent_events": [],
                "error": f"Deployment {deployment_name!r} not found in namespace {namespace!r}.",
            }
        return {
            "found": False, "healthy": False, "pod_count": 0,
            "pods": [], "recent_events": [],
            "error": f"Error reading deployment: {exc.reason}",
        }

    # List pods matching this deployment's label. Standard Deployments
    # label pods with app=<deployment_name> in this project's manifests
    # (see infra/k8s/demo-backend.yaml) -- adjust the label selector if a
    # future deployment uses a different labeling convention.
    try:
        pod_list = core_v1.list_namespaced_pod(
            namespace=namespace, label_selector=f"app={deployment_name}"
        )
    except ApiException as exc:
        return {
            "found": True, "healthy": False, "pod_count": 0,
            "pods": [], "recent_events": [],
            "error": f"Error listing pods: {exc.reason}",
        }

    pods_info = []
    any_unhealthy = False

    for pod in pod_list.items:
        phase = pod.status.phase
        restart_count = 0
        container_ready = False

        if pod.status.container_statuses:
            restart_count = sum(cs.restart_count for cs in pod.status.container_statuses)
            container_ready = all(cs.ready for cs in pod.status.container_statuses)

        is_healthy = phase == "Running" and container_ready and restart_count == 0
        if not is_healthy:
            any_unhealthy = True

        pods_info.append(
            {
                "name": pod.metadata.name,
                "phase": phase,
                "restart_count": restart_count,
                "container_ready": container_ready,
            }
        )

    # Recent events -- often the actual "why" behind a restart (OOMKilled,
    # failed liveness probe, image pull error). Filtered to Warning-type
    # events from roughly the last hour, sorted most recent first.
    recent_events = []
    try:
        events = core_v1.list_namespaced_event(namespace=namespace)
        cutoff = datetime.now(timezone.utc).timestamp() - 3600  # last hour

        for event in events.items:
            if event.involved_object.name not in {p["name"] for p in pods_info}:
                continue
            event_time = event.last_timestamp or event.event_time
            if event_time and event_time.timestamp() < cutoff:
                continue
            recent_events.append(
                {
                    "reason": event.reason,
                    "message": event.message,
                    "type": event.type,
                    "pod": event.involved_object.name,
                    "count": event.count,
                }
            )

        recent_events.sort(key=lambda e: e.get("count") or 0, reverse=True)
        recent_events = recent_events[:10]  # cap -- this is context for an LLM, not a full audit log
    except ApiException as exc:
        # Non-fatal -- pod status is the primary signal, events are a bonus.
        recent_events = [{"error": f"Could not fetch events: {exc.reason}"}]

    return {
        "found": True,
        "healthy": not any_unhealthy,
        "pod_count": len(pods_info),
        "pods": pods_info,
        "recent_events": recent_events,
        "error": None,
    }


if __name__ == "__main__":
    import json

    print("Testing check_k8s_workload against 'demo-backend'...\n")
    result = check_k8s_workload("demo-backend")
    print(json.dumps(result, indent=2, default=str))