Build plan for issue 18 demo-ready, implementing T1 through T9 exactly as decided.

One build item: writer builder, assessors business, qa and code_review, scope
app and engine plus deploy smoke script, budget 8, target main. Proofs are the
engine and app unit test suites. The decision behind this handoff: the owner
asked to skip discovery and design and open exactly this build item, so the
plan copies the assignment build phase team and the request scope, criteria
and proofs unchanged.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 8
route_overrides: {}
config_version: 12
scope:
  - app/**
  - engine/**
  - deploy/smoke.py
criteria:
  - "Implement T1-T9 exactly as decided in docs/decisions/18-demo-ready-functional.md and docs/decisions/18-demo-ready-technical.md, both merged in PRs #19 and #20."
  - "That includes the confirmed Carregar exemplo / Load example action with two idempotent example deals in future months, removal of the fixed worked example, case- and accent-insensitive matching, the next-occurrence rule for bare months, the current month taken from the Lisbon date with the env override, the no-deals page, and smoke.py creating its own deal first."
  - "The shared single-user database is accepted for the demo."
  - "Style: match propware.pt using its light-theme tokens: canvas #f6f7f4; ink #16302c; muted ink #5f6f6a; accent and focus #f2b705; accent soft #fdf3d0; soft green #a7cec0; borders #e6ebe8; danger #9e2f25 on #f6e2de; info #2f5b8a on #e4ecf5."
  - 'Fonts: no external assets. Use the stack Figtree, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Arial, sans-serif.'
  - "Primary buttons: ink background with white text, and a focus ring in the accent colour."
  - "Write tests first, and make no network calls in tests."
proof:
  - 'python3 -m unittest discover -s engine/tests -t .'
  - 'python3 -m unittest discover -s app/tests -t .'
target_branch: main
```
