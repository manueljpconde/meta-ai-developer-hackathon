Hotfix the production sign-in link crash on /auth/verify, landing on main before item 2c and item 3.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 6
config_version: 13
route_overrides: {}
scope:
  - app/web.py
  - app/auth.py
  - app/tests/**
criteria:
  - "The /auth/verify route starts the response once and redirects to / with the session cookie."
  - "The session cookie carries Secure when APP_BASE_URL is https."
  - "The test client in app/tests/helpers.py fails on a second start_response call, as wsgiref does, and a test proves a valid link signs in end to end through it."
  - "Both proof suites are green: python3 -m unittest discover -s engine/tests -t . and python3 -m unittest discover -s app/tests -t ."
proof:
  - "python3 -m unittest discover -s engine/tests -t ."
  - "python3 -m unittest discover -s app/tests -t ."
target_branch: main
```
