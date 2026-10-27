Readiness probe: deliver a short crew readiness note through the review path.

```yaml crm-plan
writer: business
assessors: [qa]
budget_usd: 3
route_overrides: {}
config_version: 4
scope:
  - docs/crew-readiness.md
criteria:
  - "`docs/crew-readiness.md` exists, has a level-one heading, and states in two or three sentences that this file was delivered by the crew as a readiness check."
proof:
  - test -s docs/crew-readiness.md && grep -q "^# " docs/crew-readiness.md
target_branch: crew-readiness
```