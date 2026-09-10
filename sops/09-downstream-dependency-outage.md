# SOP: Downstream Dependency Outage

## Summary
A service the homepage depends on (auth service, product API, payments,
etc.) is down or erroring, and the failure is propagating upstream as 5xx
errors on the homepage even though the homepage's own code and
infrastructure are healthy.

## Symptoms
- Homepage sanity check and pod health both look normal
- 5xx errors correlate with a specific downstream call in the logs
- The downstream service's own Grafana dashboard shows the actual problem

## Immediate checks

1. **Identify which downstream call is failing**
   Check application logs for the specific outbound call associated with
   the errors — this tells you which dependency to check next rather than
   guessing.

2. **Check that dependency's own health/dashboard**
   Once identified, check that service's own Grafana panels and alert
   status. It likely already has its own alert firing, or will shortly.

3. **Check for a circuit breaker or timeout misconfiguration**
   If the dependency is slow rather than fully down, check whether the
   homepage's timeout/circuit-breaker settings are appropriate — a very
   long timeout can turn a slow dependency into what looks like a full
   outage upstream.

## Likely root causes, in order of frequency

1. The downstream service itself is experiencing its own incident (check
   whether it has its own alert firing)
2. Network/DNS issue specifically between the homepage and that dependency
3. Homepage's timeout or retry configuration amplifying a minor slowdown
   into visible errors

## Escalation
This is not the homepage team's incident to own alone — loop in the
downstream service's on-call immediately once identified. The homepage
team's role here is primarily to confirm the propagation path and decide
whether a temporary fallback (serve cached/degraded content) is possible
while the dependency team resolves the actual issue.

## Related SOPs
- 5xx Error Rate Spike — Homepage
- Elevated Latency Without Errors
