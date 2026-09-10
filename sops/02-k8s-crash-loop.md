# SOP: Kubernetes Pod Crash Loop

## Summary
A workload's pods are repeatedly restarting (`CrashLoopBackOff` or high
restart count over a short window). This is one of the most common root
causes behind service-level alerts like elevated 5xx rates.

## Symptoms
- Pod status shows `CrashLoopBackOff`
- Restart count climbing rapidly (check `kubectl get pods` restart column)
- Recent Kubernetes events show `BackOff` or `Error` reasons

## Immediate checks

1. **Get pod status for the affected deployment**
   Check restart count and current pod phase. A restart count that's still
   climbing (not just historically high) means this is active, not
   historical noise.

2. **Check recent events**
   Kubernetes events for the pod/deployment often show the actual failure
   reason — OOMKilled, failed liveness probe, image pull error, etc.

3. **Check the container logs from the previous instance**
   The current (crashing) container's logs are often empty or truncated.
   Pull logs from the *previous* terminated container to see the actual
   error before it died.

4. **Check resource limits**
   If the event reason is `OOMKilled`, this is a memory limit issue, not a
   code bug necessarily — check if a recent traffic increase or a memory
   leak in a recent release is pushing past the configured limit.

## Likely root causes, in order of frequency

1. Bad config or missing environment variable/secret introduced in a
   recent deploy
2. OOMKilled — memory limit too low for current load, or a memory leak
3. Failed liveness/readiness probe due to slow startup or a dependency
   being unreachable
4. Image pull failure (wrong tag, registry auth issue)

## Escalation
If the previous container's logs show a clear application-level stack
trace tied to a recent deploy, this is a rollback candidate — escalate to
whoever owns that service's deploy pipeline rather than attempting a live
fix.

If it's OOMKilled and there's no recent deploy, this may need a resource
limit bump — escalate to the service owner with the memory usage trend
attached.

## Related SOPs
- 5xx Error Rate Spike — Homepage
- Rollback Procedure
