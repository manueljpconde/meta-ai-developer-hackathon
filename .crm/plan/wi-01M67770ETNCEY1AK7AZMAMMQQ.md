Design docs for issue 18 demo-ready flow, including owner amendments Q1-Q5 and D3/D4. Owner approves this design before Build starts.

```yaml crm-plan
phase: design
writer: architect
assessors:
  - business
  - code_review
budget_usd: 3
pool: preparation
route_overrides: {}
config_version: 11
scope:
  - docs/decisions/**
criteria:
  - write docs/decisions/18-demo-ready-technical.md, and update the functional doc to include the amendments
  - how the move reads registered deals
  - the interface between the interpretation and engine.move.move_payment
  - the prompt and response contract with muse-spark-1.3, and error handling
  - the example-loading action
  - "the CSS approach: plain CSS, no external assets, no JavaScript framework, consistent with propware.pt, works at phone width"
  - the test plan, tests first, no network calls
  - deploy/smoke.py creating its own deal first
  - the risks
  - Each decision lists its options and the reason for the choice.
proof:
  - python3 -m unittest discover -s engine/tests -t .
  - python3 -m unittest discover -s app/tests -t .
target_branch: main
```
