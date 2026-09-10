# SOP: DNS Resolution Failure

## Summary
The domain fails to resolve, or resolves to unexpected/stale IP addresses,
causing the site to be unreachable for some or all users depending on DNS
propagation state.

## Symptoms
- Sanity check tool reports DNS resolution failure
- Impact is often inconsistent across users/regions (some can reach the
  site, others can't) due to DNS caching and propagation delays
- May follow a recent DNS record change or domain/registrar-level event

## Immediate checks

1. **Confirm the failure and check what it currently resolves to**
   Run DNS resolution from the sanity check tool and compare the returned
   IP(s) against what's expected for the current infrastructure.

2. **Check for a recent DNS change**
   Look for any recent change to DNS records — a new deployment that
   updated a load balancer IP, a domain/registrar change, or an
   infrastructure migration that should have included a DNS update.

3. **Check DNS provider status**
   If no recent internal change explains it, check whether the DNS
   provider itself is reporting an incident.

4. **Check TTL on the affected record**
   A short TTL means a fix propagates fast; a long TTL means even a
   correct fix will take time to reach all users, which is important
   context for the incident timeline.

## Likely root causes, in order of frequency

1. A recent infrastructure change updated the load balancer/IP without
   updating the corresponding DNS record
2. DNS provider outage (external, not fixable from our side beyond
   waiting or failing over to a secondary provider if one exists)
3. Domain/registrar-level issue (expired domain, registrar lock issue) —
   rare, but severe when it happens

## Escalation
If it's an internal DNS record that's simply wrong, this is usually a fast
fix — correct the record and monitor propagation. If it's a provider-side
outage, escalate to whoever manages the DNS provider relationship, and
communicate the TTL-driven propagation delay clearly in the incident
thread so expectations are set correctly.

## Related SOPs
- 5xx Error Rate Spike — Homepage
- SSL Certificate Expiring or Invalid
