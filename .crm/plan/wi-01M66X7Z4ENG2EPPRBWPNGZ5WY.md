Implement issue #16 as one build item: deliver deploy/agentimo.service, deploy/Caddyfile, deploy/README.md and deploy/smoke.py so the owner can deploy on a fresh host with the Meta Model API key, and make the app report a missing or failing model key clearly without changing stored records (adding a test if uncovered). Tests must not call the network.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 10
pool: preparation
route_overrides: {}
config_version: 10
scope:
  - deploy/**
  - app/**
  - engine/**
criteria:
  - "deploy/agentimo.service: a systemd unit that runs `python3 -m app.server` from the checkout as an unprivileged user, restarts on failure, and sets `APP_HOST=127.0.0.1`, `APP_PORT` and `APP_DB_PATH` to a persistent data directory outside the checkout. It loads `META_API_KEY` (and optional `META_API_BASE_URL`) from `EnvironmentFile=/etc/agentimo/env`, which the owner creates, owned by root with mode 0600. The key must never appear in the repo, the unit or the logs."
  - "deploy/Caddyfile: an HTTPS reverse proxy to the app for one domain, given as a placeholder."
  - "deploy/README.md: the exact owner steps on a fresh Hetzner Ubuntu host (packages, user, data directory, env file, unit, Caddy, firewall, update procedure), plus the smoke test from #16."
  - "deploy/smoke.py: a standard-library script that, given a base URL, checks the first screens load and that a natural-language move (\"Move the Benfica payment to January\") returns a before/after forecast. It exits non-zero on failure."
  - "Make sure the app reports a missing or failing model key clearly and changes no stored record. Add a test if this is not already covered."
  - "Tests must not call the network. Do not change application behaviour beyond what this needs."
proof:
  - python3 -m unittest discover -s engine/tests -t .
  - python3 -m unittest discover -s app/tests -t .
target_branch: main
```
