# SOP: Database Connection Pool Exhausted

## Summary
The application's database connection pool is fully checked out, causing
new requests to queue or time out waiting for a connection, which
manifests as elevated latency or 5xx errors.

## Symptoms
- Application logs show "connection pool exhausted" or timeout errors
  waiting to acquire a connection
- Latency spikes on any endpoint that hits the database, not just one
  specific route
- Database's own active-connections metric is at or near its max

## Immediate checks

1. **Check active connection count on the database**
   Compare current active connections to the configured pool max/database
   max. If it's pinned at the ceiling, this confirms the diagnosis rather
   than something else causing the same symptom.

2. **Check for long-running or stuck queries**
   A small number of slow or stuck queries can hold connections open far
   longer than normal, starving the pool for everyone else. Check the
   database's slow query log or active query list.

3. **Check for a recent traffic increase**
   Pool exhaustion under normal traffic suggests query slowness or a leak;
   pool exhaustion only under a traffic spike suggests the pool size
   itself may just be undersized for peak load.

4. **Check for a recent deploy**
   A new code path that opens connections without releasing them properly
   (missing a `close()`/context manager) is a common regression source.

## Likely root causes, in order of frequency

1. A small number of long-running/stuck queries holding connections
2. Pool size undersized relative to current traffic
3. Connection leak introduced in a recent deploy (connections opened but
   never released)

## Escalation
If a specific stuck query is identified, that can sometimes be killed
directly to free up the pool as an immediate mitigation — coordinate with
whoever owns that database before doing this. If it's a sizing issue,
escalate to the service owner for a pool size increase; if it's a leak,
this is a rollback candidate.

## Related SOPs
- 5xx Error Rate Spike — Homepage
- Elevated Latency Without Errors
- Rollback Procedure
