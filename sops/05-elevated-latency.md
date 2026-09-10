# SOP: Elevated Latency Without Errors

## Summary
Response times are elevated but the service isn't returning errors — users
experience slowness rather than outright failures. Distinct from the 5xx
runbook because the failure mode and likely causes are different.

## Symptoms
- P95/P99 latency panel shows a sustained increase
- Error rate stays normal (low or zero)
- Users may describe the site as "slow" or "hanging" rather than "down"

## Immediate checks

1. **Check if it's isolated to one endpoint or site-wide**
   Site-wide slowness points toward infrastructure (network, database,
   shared dependency). A single-endpoint issue points toward that
   endpoint's specific code path or a downstream call it makes.

2. **Check downstream dependency latency**
   If the homepage calls the product API or auth service, check their
   latency panels too — the homepage may just be waiting on a slow
   dependency, not actually be the problem itself.

3. **Check database query performance**
   Sudden latency increases with no code change often trace back to a
   slow query — a new query pattern, a missing index, or a lock
   contention issue during a batch job.

4. **Check current traffic level**
   Compare current request volume to the normal baseline for this time of
   day. A traffic spike can produce latency increases even with
   healthy infrastructure, if autoscaling hasn't caught up yet.

## Likely root causes, in order of frequency

1. Slow downstream dependency (not the service itself)
2. Database query performance regression
3. Traffic spike outpacing current pod count / autoscaling lag
4. Resource contention (CPU throttling) on underprovisioned pods

## Escalation
If it's isolated to a single downstream dependency, loop in that service's
owner directly rather than continuing to investigate from the homepage
side. If it's a database issue, loop in whoever owns that database
instance — this typically isn't something to resolve from the application
layer alone.

## Related SOPs
- 5xx Error Rate Spike — Homepage
