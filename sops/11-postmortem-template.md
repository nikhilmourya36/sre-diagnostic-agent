# SOP: Postmortem Template

## Summary
Standard structure for writing up an incident after it's resolved. Applies
to any incident that triggered a PagerDuty page, regardless of root cause.

## When to write one
Any incident that paged on-call, or any incident visible to users for more
than a few minutes, even if it didn't page (e.g. caught and fixed quickly
by a sharp-eyed engineer).

## Sections to include

### Summary
One or two sentences: what broke, for how long, and who/what was
affected. Written so someone outside the team can understand it without
context.

### Timeline
Chronological list of key events with timestamps — alert fired, on-call
acknowledged, diagnosis steps taken, mitigation applied, resolution
confirmed. Pull actual timestamps from Grafana/PagerDuty/Slack rather than
reconstructing from memory.

### Root cause
The actual underlying cause, not just the symptom. "5xx errors" is a
symptom; "a deploy introduced a connection leak that exhausted file
descriptors after 6 hours" is a root cause.

### Impact
Concretely: how many users/requests affected, for how long, any revenue or
downstream impact if known.

### What went well
Things that worked during the response — fast detection, correct
diagnosis, an SOP that was accurate and helped, good communication.

### What could be improved
Gaps in monitoring, missing or inaccurate SOPs, slow diagnosis steps,
anything that made the response harder than it should have been.

### Action items
Concrete follow-ups with owners and rough timelines — not vague intentions.
Each item should be specific enough to become a ticket as-is.

## Notes
Postmortems are blameless — the goal is understanding the system and
process, not assigning fault to an individual. Keep the language focused
on what happened and what to change, not who did something wrong.

## Related SOPs
- Rollback Procedure
