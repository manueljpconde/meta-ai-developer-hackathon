Refuse unknown keys in an engine part, test first, starting from main. Tests are committed before the change so the first commit fails; only files under engine/ change.

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
  - "WHAT TO CHANGE: a part's allowed keys are exactly part_base, iva_rate, retencao_rate, irs_rate, ss_rate and other_rates. Any other key is refused with ValueError, and the message names the key."
  - 'WHAT TO CHANGE: keys stay case-sensitive: "IVA_rate" is an unknown key, not an alias.'
  - 'WHAT TO CHANGE: a missing optional rate key still means a rate of "0": a part without retention omits retencao_rate. Only part_base is required, as now.'
  - "WHAT TO CHANGE: every existing test keeps passing unchanged, including the six vectors A to F, and ENGINE_VERSION stays 1."
  - 'TESTS: add to engine/tests/test_properties.py, committed and pushed before the change so the first commit fails: calc_month([{"part_base": 100000, "IVA_rate": "0.23"}]) raises ValueError whose message contains IVA_rate.'
  - 'TESTS: calc_month([{"part_base": 100000, "iva_rate": "0.23", "note": "x"}]) raises ValueError whose message contains note.'
  - 'TESTS: calc_month([{"part_base": 100000}]) returns commission 100000, bank_inflow 100000, protected_money 0 and really_available 100000 (optional keys still default to 0).'
  - "ASSESSMENT QA: every test in section 3 is present and passes at the head, the vectors still pass, and the first two tests fail at the tests-only commit. Also try inputs beyond the listed tests (a key that differs only in case, a key with surrounding spaces, a non-string key, an empty part {}), and report what each one does."
  - "ASSESSMENT code review: the diff touches only engine/calc.py and engine/tests/test_properties.py, with no new dependency and no change to rounding or the money path."
  - "ASSESSMENT business: the four monthly amounts and vectors A to F are unchanged."
proof:
  - python3 -m unittest discover -s engine/tests -t . -v
target_branch: main
```
