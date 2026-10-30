Build plan version 2 for wi-01M66MD6VCDBPQBAGT29SJ056S, reusing the existing item for the build phase per owner reply seq 1532 (skip discovery and design; one build item with writer builder and assessors business, qa, code_review).

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 5
pool: preparation
route_overrides: {}
config_version: 10
scope:
  - 'engine/**'
  - 'app/**'
criteria:
  - 'Add natural-language input to the Cash-flow Scenario Assistant from issue #2, for the move operation only.'
  - 'The agent types a sentence such as "Move the Benfica payment to January"; a Meta Model API call (model `muse-spark-1.3`) turns it into a structured move (deal reference, payment, target month), which is passed to the existing `engine.move.move_payment` and shown as the before/after forecast.'
  - 'If the sentence is ambiguous or names an unknown deal or payment, ask one focused question instead of guessing.'
  - 'Never change stored records.'
  - 'Put the model call behind a small client interface with the API key read from the environment, never from code.'
  - 'Tests must not call the network: use a fake client for the interpretation, and cover a clear move, an ambiguous one, an unknown deal, and a model failure.'
  - 'Write the tests first.'
proof:
  - 'python3 -m unittest discover -s engine/tests -t .'
  - 'python3 -m unittest discover -s app/tests -t .'
target_branch: main
```
