Refuse two invalid engine inputs with ValueError: non-finite rates and parts without part_base. Tests first, then the fix.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 5
pool: null
route_overrides: {}
config_version: 8
scope:
  - engine/**
criteria:
  - 'calc_part(100000, r) raises ValueError for each r in "NaN", "sNaN", "Infinity", "-Infinity".'
  - 'calc_month([{"part_base": 100000, "iva_rate": "NaN"}]) raises ValueError.'
  - 'calc_month([{"iva_rate": "0.23"}]) raises ValueError.'
proof:
  - python3 -m unittest discover -s engine/tests -t . -v
target_branch: main
```
