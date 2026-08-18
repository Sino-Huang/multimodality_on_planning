---
status: accepted
---

# Use local LAMA-first for Planimation production

CGAS production rendering must generate each plan locally with
`modules/downward/fast-downward.py --alias lama-first` and submit that plan to
Planimation as a supplied plan. Planimation is only the plan interpreter and
VFG/PNG renderer: it must never invoke its default hosted solver, and a missing
or failed local plan must become an explicit terminal planning failure before
any Planimation HTTP request. This replaces the aborted attempt-001 behavior,
where missing supplied plans caused the local backend to delegate planning to
the hosted `dual-bfws-ffparser` service.
