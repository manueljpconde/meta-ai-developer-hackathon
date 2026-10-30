Build work item for issue #2: move-payment scenario operation. Writer is builder; assessors are business, qa and code_review. Scope is engine/** and app/** on target branch main, with the two owner-given proof commands.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 8
pool: preparation
route_overrides: {}
config_version: 9
scope:
  - engine/**
  - app/**
criteria:
  - 'Add the first Cash-flow Scenario Assistant operation from issue #2: "move a selected unpaid expected payment to another month".'
  - In the engine, add a pure function that takes the agent's current records and a move (deal reference, payment, target month) and returns the recalculated forecast without changing stored records.
  - 'Refuse ambiguous or invalid moves: unknown deal, payment already received, past month.'
  - Write the tests first.
  - Show the before and after forecast in the app for one example.
  - Do not call any model yet, and do not change how records are saved.
proof:
  - python3 -m unittest discover -s engine/tests -t .
  - python3 -m unittest discover -s app/tests -t .
target_branch: main
```