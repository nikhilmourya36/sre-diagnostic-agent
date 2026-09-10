# SOP: Rollback Procedure

## Summary
Standard procedure for rolling back a service to its previous known-good
version, once a recent release has been identified as the likely cause of
an incident.

## When to use this
- A recent release (within the last 24h) correlates in time with the
  incident's onset
- The affected service or a direct dependency was the one deployed
- Root cause is not yet confirmed, but the risk of continued impact
  outweighs the time needed to fully diagnose

## Steps

1. **Confirm the previous stable version**
   Check deployment history for the last known-good release — the one
   immediately before the suspected bad deploy.

2. **Notify before acting**
   Post in the incident thread that a rollback is starting, which service,
   and which version you're rolling back to. This avoids someone else
   deploying over your rollback mid-action.

3. **Execute the rollback**
   Use the standard deploy tooling to redeploy the previous version — do
   not attempt to manually patch forward under incident pressure unless
   the fix is trivial and well understood.

4. **Verify recovery**
   Watch the relevant Grafana panel (error rate, latency, or whichever
   metric triggered the alert) for 5-10 minutes post-rollback to confirm
   it returns to baseline before declaring the incident resolved.

5. **Do not delete the bad release**
   Keep the rolled-back version's artifacts and logs available — they're
   needed for the postmortem.

## After the rollback
- Resolve the PagerDuty incident once metrics are confirmed stable
- Leave a note in the incident thread summarizing what was rolled back and
  why
- File a follow-up ticket for root-causing the bad release properly; a
  rollback buys time, it doesn't replace the postmortem

## Related SOPs
- 5xx Error Rate Spike — Homepage
- Kubernetes Pod Crash Loop
