Build item 1 of 4: sign-in and sessions, starting from branch wip/accounts-1 (7e3d47b) and landing on main.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 24
route_overrides: {}
config_version: 13
scope:
  - app/**
  - engine/**
criteria:
  - 'Email-link sign-up and sign-in, link hashing, single use, 15-minute expiry, per-email and per-IP limits, the sign-in button page, 30-day fixed sessions with hashed ids, sign-out on the device, mail through the PropWare relay. Technical acceptance criteria 1-3.'
  - 'The decision documents are binding; where this request is silent, they decide.'
  - 'Criterion 15 (both proof suites green) applies to every item.'
  - 'Python standard library only, as today. No external scripts or assets in pages, except the small inline recording script the design allows.'
  - 'Tests first; no network calls in tests (stub the model, transcription and SMTP).'
proof:
  - python3 -m unittest discover -s engine/tests -t .
  - python3 -m unittest discover -s app/tests -t .
target_branch: main
```
