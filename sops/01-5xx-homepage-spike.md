# SOP: 5xx Error Rate Spike — Homepage

## Summary
This runbook covers a sudden increase in 5xx responses on the homepage
service, as detected by the Grafana alert `homepage-5xx-rate-high`.

## Symptoms
- Grafana alert fires for 5xx rate exceeding threshold (typically >2% of
  requests over a 5 minute window)
- Users may report the site as "down" or "erroring" in Slack
- Homepage load times may or may not be elevated alongside the errors

## Immediate checks (do these first)

1. **Confirm it's real, not a monitoring blip**
   Run a manual HTTP check against the homepage URL. If you get a clean
   200, treat this as a possible false alarm and check the Grafana panel
   for a single-datapoint spike vs. a sustained trend.

2. **Check pod health**
   Look at the homepage deployment's pod status. Restart counts or pods
   stuck in `CrashLoopBackOff` are the most common root cause for this
   alert.

3. **Check recent releases**
   Look at the `#releases` channel or deployment history for the last 24
   hours. A high proportion of 5xx spikes correlate with a release to the
   homepage service or one of its direct dependencies (auth service,
   product API).

4. **Check open file descriptor count**
   If pods are healthy and there's no recent release, check the "Open File
   Descriptors" panel on the homepage Grafana dashboard. A slow climb
   followed by a spike often indicates a connection leak (see the FD
   Exhaustion SOP for the full procedure).

## Likely root causes, in order of frequency

1. Bad deploy to homepage service or a direct dependency
2. Pod crash-looping due to a bad config or missing secret
3. Downstream dependency (auth service, product API) returning errors that
   propagate as 5xx
4. File descriptor / connection pool exhaustion under load

## Escalation
If pods are healthy, no recent release, and the sanity check tool confirms
sustained 5xx over 3+ minutes, page the on-call backend engineer directly
rather than continuing to investigate alone — this pattern usually needs
someone with deploy access to roll back.

## Related SOPs
- Kubernetes Pod Crash Loop
- File Descriptor Exhaustion
- Rollback Procedure
