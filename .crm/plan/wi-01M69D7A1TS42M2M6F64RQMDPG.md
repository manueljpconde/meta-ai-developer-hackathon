Item 2b, isolation hardening: follow-up to item 2 starting from main with item 2 merged, landing on main before item 3 starts.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 12
route_overrides: {}
config_version: 13
scope:
  - "**"
criteria:
  - "Remove every committed __pycache__/*.pyc file and add __pycache__/ and *.pyc to .gitignore."
  - "Web-route tests where agent B sends agent A's deal id to every route that changes a deal (edit, move scenario, confirm update), proving no data is returned and A's deal is unchanged."
  - "The deletion test goes through the typed-address page and proves no row of any kind remains for the tenant, including sign-in links, sessions and rate-limit rows."
  - "Both proof suites green."
proof:
  - "python3 -m unittest discover -s engine/tests -t ."
  - "python3 -m unittest discover -s app/tests -t ."
target_branch: main
```
