Fix the four PR #11 defects test-first, starting from main, changing only engine/ and app/.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 8
pool: null
route_overrides: {}
config_version: 8
scope:
  - engine/**
  - app/**
criteria:
  - |-
    `engine/calc.py` gains `agent_share(agency_base, share_rate)`. It returns integer cents, `round(agency_base × share_rate)` half-up with exact decimals, and validates its inputs like the existing functions do (integer cents, a decimal-string rate between 0 and 1, `ValueError` or `TypeError` as they already use). `ENGINE_VERSION` stays 1, and every existing engine test passes unchanged.
  - |-
    `app/web.py` uses `engine.calc.agent_share` and removes `derive_share`, so the app performs no money arithmetic.
  - |-
    `unescape_fields` is removed. Form values reach validation and storage exactly as submitted. Output escaping is unchanged.
  - |-
    Request bodies over 64 KiB are refused with 413 before being read, and nothing is saved.
  - |-
    A body that isn't valid UTF-8 is refused with 400, and nothing is saved.
  - |-
    Text fields have limits: deal name and agency name at most 200 characters each. Over the limit, the field is refused beside it, in both languages, and nothing is saved.
  - |-
    Write these first, and commit and push them before the fix. At least the tests for points 1, 2 and 3 must fail on that commit by assertion, not by an import error. (Point 1's test can call the new function through the app, and check that a fixed agency commission and rate give a share computed by the engine; or assert that `app/web.py` has no `derive_share`. Choose one that fails by assertion.)
  - |-
    `agent_share(1000000, "0.5")` gives `500000`.
  - |-
    `agent_share(1001, "0.5")` gives `501` (500.5 rounds half-up).
  - |-
    `agent_share(100000, "0.333")` gives `33300`.
  - |-
    `agent_share(100000, 0.5)` (a float) gives `TypeError`.
  - |-
    `agent_share(100000, "1.5")` and `agent_share(-1, "0.5")` give `ValueError`.
  - |-
    The app's share for the UX example (10 000,00 € at 50 %) is 5 000,00 €, computed through `engine.calc.agent_share`.
  - |-
    A deal named `&lt;b&gt;` confirmed, then read back from the store is stored exactly as `&lt;b&gt;`, and shown on the page as the escaped text `&amp;lt;b&amp;gt;`.
  - |-
    A POST with `CONTENT_LENGTH` 65537 gives 413; nothing saved; the body isn't read.
  - |-
    A POST whose body is not valid UTF-8 gives 400; nothing saved.
  - |-
    A deal name of 201 characters is refused beside the field, in `pt-PT` and in `en-GB`; nothing saved.
  - |-
    A deal name of 200 characters is accepted.
  - |-
    Every existing app and engine test still passes.
  - |-
    QA: every check in section 3 is present and passes at the head, and the tests for points 1–3 fail by assertion at the tests-only commit. Also try inputs beyond the listed tests (a `CONTENT_LENGTH` that isn't a number, a negative `CONTENT_LENGTH`, an agency name of 201 characters, a share rate of `"0"` and `"1"`), and report what each one does.
  - |-
    Code review: no money arithmetic in `app/`; `agent_share` follows the engine's existing validation style; no `html.unescape` on input anywhere; the body limit is enforced before reading; no change to `prototype/`.
  - |-
    Business: "A tua parte" and the four amounts for the UX example are unchanged on every screen, in both languages.
proof:
  - python3 -m unittest discover -s engine/tests -t . -v
  - python3 -m unittest discover -s app/tests -t . -v
target_branch: main
```
