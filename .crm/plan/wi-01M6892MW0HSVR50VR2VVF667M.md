Close the last gap of issue 18: add the move scenario to the navigation, test first.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 2
route_overrides: {}
config_version: 12
scope:
  - 'app/**'
criteria:
  - 'In `app/web.py`, add a fourth navigation link to `/scenarios/move`, after "Novo negócio" and before "Definições", with `data-i18n="nav_move"`.'
  - 'In `app/i18n.py`, add `nav_move`: Portuguese "Mover pagamento", English "Move payment".'
  - 'Mark the link as current on `/scenarios/move`, the same way the other links are marked, if they are.'
  - 'Write the test first: every page that renders the navigation contains a link to `/scenarios/move` with the correct label in each language. Make no network calls in tests.'
proof:
  - 'python3 -m unittest discover -s engine/tests -t .'
  - 'python3 -m unittest discover -s app/tests -t .'
target_branch: main
```
