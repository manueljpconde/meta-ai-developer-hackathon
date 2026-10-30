Discovery for issue #18: functional decisions document making the live product demo-ready, written to docs/decisions/18-demo-ready-functional.md. First of three sequential phases; design and build follow only after the owner approves this phase.

```yaml crm-plan
phase: discovery
writer: business
assessors:
  - qa
  - architect
budget_usd: 3
route_overrides: {}
config_version: 10
scope:
  - docs/decisions/18-demo-ready-functional.md
criteria:
  - "the agent's journey from first visit to the move scenario;"
  - "how a sentence identifies one of the agent's own deals and payments, including partial names, two deals that match, an unknown deal, and a deal with no expected payments;"
  - "the no-deals state;"
  - "what the forecast shows before and after;"
  - "Portuguese and English wording;"
  - "what is out of scope."
  - "Each decision lists the options considered and why one was chosen."
  - "Questions only I can answer go to me as owner questions, not guesses."
proof:
  - "python3 -m unittest discover -s engine/tests -t ."
  - "python3 -m unittest discover -s app/tests -t ."
target_branch: main
```
