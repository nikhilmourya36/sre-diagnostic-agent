# SOP: SSL Certificate Expiring or Invalid

## Summary
The SSL/TLS certificate for a service is expired, about to expire, or
otherwise invalid, causing browser warnings or outright connection
failures for users.

## Symptoms
- Sanity check tool reports SSL check as failed or warning
- Users report browser security warnings ("connection not private")
- Some HTTP clients/integrations may fail outright with certificate
  validation errors while browsers show a warning but allow bypass

## Immediate checks

1. **Confirm expiry status and exact date**
   Run the SSL check against the affected domain and note the exact
   expiry timestamp — this determines urgency (already expired vs.
   expiring soon).

2. **Check certificate renewal automation**
   Most services use an automated renewal process (e.g. cert-manager on
   Kubernetes, or a Let's Encrypt cron job). Check whether that automation
   ran recently and whether it succeeded or failed silently.

3. **Check for a recent infra change**
   Cert issues are often triggered by an unrelated infra change — a load
   balancer reconfiguration, a DNS change, or an ingress controller update
   that broke the renewal path.

## Likely root causes, in order of frequency

1. Automated renewal job failed silently (permissions, rate limit from the
   CA, DNS validation failure) and nobody caught it before expiry
2. Certificate was manually issued and nobody set a renewal reminder
3. A recent ingress/load-balancer change pointed traffic at a config
   without the updated certificate attached

## Escalation
This is time-sensitive once expired — users are actively seeing warnings
or failures. Escalate immediately to whoever owns the certificate
automation/infra, since this typically requires infra-level access to fix,
not an application-level change.

## Related SOPs
- 5xx Error Rate Spike — Homepage
