Engine build plan for probe-14: package engine/ at the repository root with integer cents, exact decimal rates, half-up rounding per component, pure per-part and monthly functions, ENGINE_VERSION = 1, and unittest vectors from the request, tests committed before the implementation. No pool is used.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 20
route_overrides: {}
config_version: 8
scope:
  - 'engine/**'
criteria:
  - 'Package engine/ at the repository root: engine/__init__.py, engine/calc.py, tests under engine/tests/.'
  - 'Money is integer cents everywhere. A float anywhere in the money path is a defect, including in tests.'
  - 'Rates are exact decimals given as strings (for example "0.23") and parsed with decimal.Decimal; a float rate is refused with TypeError.'
  - 'Rounding is half-up to the cent (ROUND_HALF_UP), applied to each component independently, exactly at the boundaries section 5.1 defines.'
  - 'ENGINE_VERSION = 1, exposed by the package (section 5.4).'
  - 'A pure function per part returning, as integer cents: iva, retencao, bank_inflow, irs_target, irs_reserve, ss_reserve, each named other reserve, and protected_money.'
  - 'A pure monthly function returning the four amounts of section 5.5 (commission, bank_inflow, protected_money with its breakdown, really_available), summing the parts cent components without re-rounding (5.2), with really_available = bank_inflow − protected_money − expenses.'
  - 'really_available may be negative; it is returned as is, never clamped.'
  - 'Inputs that are not valid are refused with ValueError: a negative part base, a rate outside 0 to 1, a negative expense, a non-integer amount.'
  - 'No I/O, no clock, no global state. Same inputs, same outputs.'
  - 'The first commit on the work branch adds the tests only, and they fail against it (the engine does not exist yet). The implementation follows in later commits.'
  - 'Case A: retencao exceeds the IRS target | part_base 500000 | iva 0.23 | retencao 0.25 | irs 0.20 | ss 0.214 | other none | expenses 30000 | Expected iva 115000, retencao 125000, bank_inflow 490000, irs_target 100000, irs_reserve 0, ss_reserve 107000, protected 222000, really_available 238000'
  - 'Case B: half-up at .5 | part_base 12350 | iva 0.23 | retencao 0 | irs 0 | ss 0 | other none | expenses 0 | Expected iva 2841 (2840.5 rounds up; banker rounding would give 2840), bank_inflow 15191'
  - 'Case C: IRS above retencao | part_base 200000 | iva 0.23 | retencao 0.11 | irs 0.25 | ss 0 | other none | expenses 0 | Expected iva 46000, retencao 22000, bank_inflow 224000, irs_target 50000, irs_reserve 28000, protected 74000, really_available 150000'
  - 'Case D: a named other reserve | part_base 100000 | iva 0 | retencao 0 | irs 0 | ss 0 | other "fundo": 0.05 | expenses 0 | Expected other "fundo" 5000, protected 5000, bank_inflow 100000, really_available 95000'
  - 'Case E: zero base | part_base 0 | iva 0.23 | retencao 0.25 | irs 0.20 | ss 0.214 | other none | expenses 0 | Expected every component 0'
  - 'Case F: negative really available | part_base 100000 | iva 0.23 | retencao 0 | irs 0 | ss 0 | other none | expenses 200000 | Expected bank_inflow 123000, protected 23000, really_available −100000'
  - 'Also test: that the four amounts stay distinct keys even when two values coincide (5.5); that the monthly sum is not re-rounded; that float inputs and the invalid inputs above are refused.'
  - 'QA: every vector above is present and passes; the history shows tests committed before the code they cover.'
  - 'Business: the four amounts and their definitions match section 5.5; nothing presents bank inflow as available money.'
  - 'Code review: integer cents and Decimal throughout, half-up per component, no float, no I/O, no dependency outside the standard library.'
proof:
  - 'python3 -m unittest discover -s engine/tests -t . -v'
target_branch: main
```