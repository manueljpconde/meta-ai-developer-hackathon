Fix scientific-notation pre-filled percentages in the agent app.

The stored rates shown by format_edit_percent in app/web.py render as exponents such as 5E+1. This breaks the new-deal form and the settings form when values are submitted unchanged. The work fixes the formatter to plain decimal digits and adds regression tests for the formatter, the round trip, and the pre-filled journeys in both languages.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 5
pool: null
route_overrides: {}
config_version: 8
scope:
  - "app/**"
criteria:
  - "WHAT TO CHANGE: format_edit_percent(rate, lang) returns plain decimal digits, never an exponent, with no trailing zeros and the locale's decimal separator (foundation 14.3, 'Percentage, while editing': 12,5 in pt-PT, 12.5 in en-GB)."
  - "WHAT TO CHANGE: A value it produces, submitted unchanged, parses back to exactly the same stored rate (parse_percent round trip)."
  - "REQUIRED TESTS: Write these first, and commit and push them before the fix, so the first commit fails by assertion (not by an import error)."
  - "REQUIRED TESTS: format_edit_percent of '0.5', '0.1', '0.3', '1', '0.23', '0.125', '0' in pt-PT gives 50, 10, 30, 100, 23, 12,5, 0."
  - "REQUIRED TESTS: The same in en-GB gives 50, 10, 30, 100, 23, 12.5, 0."
  - "REQUIRED TESTS: No output for any rate in the table contains E or e."
  - "REQUIRED TESTS: Round trip - for every rate in the table and both languages, parse_percent(format_edit_percent(rate, lang), lang) / 100 equals the rate."
  - "REQUIRED TESTS: Pre-filled journey - save the UX example settings (share 50 %, IVA 23 %, retencao 25 %, IRS 30 %, Seguranca Social 10 %, expenses 350,00 EUR) through the settings form; open the new-deal form; submit it with the pre-filled percentage left unchanged, adding only name, commission 10000,00, November 2026 and Confirmado; the review page shows A tua parte 5 000,00 EUR and no field error."
  - "REQUIRED TESTS: Settings round trip - open the settings form after saving the example, and submit it unchanged; accepted; the stored settings are identical."
  - "REQUIRED TESTS: Both pre-filled checks in en-GB give the same results."
  - "REQUIRED TESTS: Every existing app and engine test still passes."
  - "ASSESSMENT QA: every check in section 3 is present and passes at the head, and the formatter and pre-filled tests fail by assertion at the tests-only commit. Also go through the whole journey as an agent would, submitting every pre-filled form unchanged (settings, new deal, review, confirm), in both languages, and report anything that is refused or displayed wrongly."
  - "ASSESSMENT Code review: the formatter never produces an exponent for any Decimal it can receive; no change outside app/; no money arithmetic added."
  - "ASSESSMENT Business: the pre-filled journey with the UX example works in both languages without retyping any value."
proof:
  - "python3 -m unittest discover -s engine/tests -t . -v"
  - "python3 -m unittest discover -s app/tests -t . -v"
target_branch: main
```
