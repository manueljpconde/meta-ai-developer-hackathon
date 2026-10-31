Build item 2 of 4: tenant scoping and isolation, starting from main with item 1 merged. One writer builds it, three assessors judge it, and it lands on main before item 3 starts.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 24
route_overrides: {}
config_version: 13
scope:
  - "app/**"
  - "engine/**"
criteria:
  - "Every row carries its tenant and every query is scoped by it."
  - "Tests prove that one agent cannot read or change another agent's deals, notes or settings, including by guessing ids."
  - "Account deletion with typed-address confirmation."
  - "A guessed or another tenant's identifier, on any read or write route, yields no data and changes nothing."
  - "Deleting the account runs only when the typed address matches, then leaves no row of any kind for the tenant, with no recovery."
  - "The session gate blocks by default: every route requires a signed-in agent except an explicit public list (sign-in, link verification, the stylesheet, language choice). A test enumerates all routes and proves each one outside the list redirects to sign-in."
  - "Rows without a tenant (pre-existing data) are visible to no tenant."
  - "Criterion 15 (both proof suites green) applies to every item."
proof:
  - "python3 -m unittest discover -s engine/tests -t ."
  - "python3 -m unittest discover -s app/tests -t ."
target_branch: main
```
