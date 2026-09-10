# SOP: File Descriptor Exhaustion

## Summary
A slow, steady climb in open file descriptors (FDs) that eventually causes
connection failures and 5xx errors once the process hits its FD limit.
Distinct from a sudden crash — this pattern builds over hours, not
minutes.

## Symptoms
- Grafana "Open File Descriptors" panel shows a steady upward trend, not a
  sudden spike
- 5xx errors begin once FD count approaches the configured `ulimit`
- Errors often mention "too many open files" in application logs
- Restarting the affected pod temporarily resolves it (FD count resets),
  which can mask the underlying leak if on-call only restarts without
  investigating

## Immediate checks

1. **Confirm the pattern**
   Check the FD count trend over the last 6-12 hours, not just the current
   value. A gradual climb (not a step change) is the signature of this
   issue specifically.

2. **Correlate with deploy history**
   Check whether the climb started at or shortly after a specific
   deployment. A new leak almost always traces back to a code change that
   opens a connection/file/socket without closing it (common culprits:
   unclosed HTTP client connections, unclosed DB connections, unclosed
   file handles in a logging or upload path).

3. **Check which resource type is leaking**
   If available, check `/proc/<pid>/fd` on the affected pod to see whether
   the leaking FDs are sockets, files, or pipes — this narrows down which
   part of the codebase to look at.

## Likely root causes, in order of frequency

1. HTTP client (outbound calls to a dependency) not reusing connections or
   not closing them on error paths
2. Database connection pool misconfigured or not returning connections
3. File handles opened during upload/logging paths not being closed

## Escalation
This is not typically a false alarm — if the trend is confirmed and
climbing, escalate to the service owner with the deploy correlation
attached. A pod restart is a valid short-term mitigation to buy time, but
should be explicitly called out as temporary, not a fix, in the incident
notes.

## Related SOPs
- 5xx Error Rate Spike — Homepage
- Kubernetes Pod Crash Loop
