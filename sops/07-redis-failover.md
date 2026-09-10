# SOP: Redis Failover / Connection Issues

## Summary
Redis (used for caching and/or session storage) becomes unreachable or
fails over to a replica, causing elevated errors or degraded performance
in services that depend on it.

## Symptoms
- Application logs show Redis connection timeouts or refused connections
- Cache-dependent endpoints slow down significantly (cache misses forcing
  fallback to the database) or start erroring outright if the code has no
  fallback path
- Session-related issues (users getting logged out unexpectedly) if Redis
  backs session storage

## Immediate checks

1. **Check Redis instance health directly**
   Confirm whether the primary Redis instance is reachable and responsive.
   A failover event usually has a clear marker in Redis's own logs/events.

2. **Check which services depend on this Redis instance**
   Multiple services may share a Redis instance — a Redis issue can look
   like several unrelated service alerts firing at once. Check whether
   other alerts fired in the same window.

3. **Check application-level fallback behavior**
   Some services are built to gracefully degrade (skip cache, hit the
   database directly) when Redis is unavailable. Confirm whether the
   affected service has this fallback — if it doesn't, that's the actual
   bug to flag post-incident, not just "Redis was down."

## Likely root causes, in order of frequency

1. Redis primary node failure triggering an automatic failover, with a
   brief connection gap during the transition
2. Redis running out of memory (eviction policy misconfigured or genuine
   capacity issue)
3. Network partition between the application and Redis (rare, usually
   infra-level)

## Escalation
If failover already completed and services recovered on their own, this
may not need active intervention — confirm recovery and document the
event. If Redis is still down or repeatedly failing over, escalate to
whoever owns the Redis infrastructure immediately, since this is usually
outside application-team control.

## Related SOPs
- Elevated Latency Without Errors
- 5xx Error Rate Spike — Homepage
