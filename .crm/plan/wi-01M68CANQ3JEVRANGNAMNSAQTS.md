Fix hackathon issue 23 move scenario for user-entered deals, covering the five Expected points and every acceptance test in the issue, tests first.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 3
config_version: 12
route_overrides: {}
scope:
  - "app/**"
  - "engine/**"
criteria:
  - "Implement the five \"Expected\" points and every acceptance test in issue #23 exactly."
  - "When the matched deal has exactly one unpaid payment, use that payment whatever the model returned; with more than one, ask which, listing the payments by month. Name each deal's payment in the model context (`engine/model_client.py` `build_interpret_context`)."
  - "Show an engine refusal as one plain question in the page's language, never the raw error text."
  - "On submit of the move form, disable the button and show \"A simular…\" (pt-PT) / \"Simulating…\" (en-GB). Keep it inline: no external scripts or assets."
  - "Serve requests concurrently in `app/server.py` (for example a threading WSGI server from the standard library), so a slow model call does not block other requests."
  - "Questions shown in Portuguese are fully Portuguese."
  - "Standard library only."
  - "Write the tests first, and make no network calls in tests."
proof:
  - "python3 -m unittest discover -s engine/tests -t ."
  - "python3 -m unittest discover -s app/tests -t ."
target_branch: main
```