# Demo-ready technical decisions (issue #18)

Status: design for owner approval. No build follows until approved.
Scope: how the approved functional behaviour is implemented; product code
is untouched by this document.

Sources: verified against the code and tests on the target branch
(`app/web.py`, `app/i18n.py`, `app/store.py`, `app/static/style.css`,
`engine/move.py`, `engine/nl_move.py`, `engine/model_client.py`,
`deploy/smoke.py`, and the suites under `app/tests/` and
`engine/tests/`). Anything not verifiable there is marked as an
assumption or as not verified. Nothing below was guessed.

Binding owner amendments applied: Q1 (example-loading action creating
example settings and two deals), Q2 (every registered deal is movable
expected money), Q3 (no fixed worked example; example data comes only
from Q1), Q4 (matching ignores case and accents; two remaining matches
produce a question naming both with their months), Q5 (a month without
a year means its next occurrence from the current month), D3/D4 (with
no deals, the move page says so and links to New deal and the Q1
action).

## T1. How the move reads registered deals

Decision: reuse `nl_records_from_deals` in `app/web.py` unchanged as
the only reader. Each stored deal becomes exactly one record:
`deal` from the stored name, `payment` always `part-1`, `month` from
the stored deal month, `part_base` from the stored share cents,
`received` always false, and the four rate keys frozen at confirmation
time. Per Q2, every registered deal is therefore movable expected
money, and received-state tracking stays out of scope.

Options considered: (a) reuse the existing reader unchanged; (b) write
a new reader that re-derives figures from settings at move time.
Chosen (a): the stored rows already carry the frozen rates used at
confirmation, so re-deriving would show figures the review page never
showed; reuse keeps the scenario consistent with what the agent
confirmed, and it is already covered by the scenario tests.

## T2. Interface between the interpretation and `engine.move.move_payment`

Decision: `plan_nl_move` in `engine/nl_move.py` stays the single
boundary, with this contract:

- Input: the raw sentence, the records from T1, the current month
  (`YYYY-MM`, see T7), an `interpret` callable, and expenses in cents.
- `interpret` returns either a move dict (`deal`, `payment`,
  `target_month`) or a `{"question": ...}` dict for a sentence that is
  itself ambiguous.
- Shape validation stays inside `plan_nl_move`, before any engine
  call: non-string or blank sentence asks which payment and month
  without calling the model; missing deal or payment asks which
  payment; a target that is not `YYYY-MM` asks which month, naming the
  deal and payment. Only a well-shaped move reaches `move_payment`
  with positional arguments `(records, move, current_month,
  expenses_cents=...)`.
- Every `ValueError` from `move_payment` (unknown deal, unknown
  payment, received payment, past target, ambiguity) becomes one
  focused question; it never propagates. Every exception from
  `interpret` becomes an error, never a question and never a guess.
- Nothing stored ever changes: the engine call is pure and the given
  records are only read, as the existing tests assert by snapshot.

Options considered: (a) validate in the web layer and let the engine
raise; (b) keep validation inside `plan_nl_move`. Chosen (b): the
rule "no guess, one question" is then testable without the WSGI app,
and the existing suites already pin it there.

## T3. Prompt and response contract with the interpretation model, and error handling

Decision: keep the live client `MetaMoveClient` in
`engine/model_client.py` with model `muse-spark-1.3`, standard library
only (`urllib`), temperature 0, and the API key read from the
`META_API_KEY` environment variable or passed explicitly, never
written in code.

- Request: `POST {base}/chat/completions` with `{model, messages:
  [system, user], temperature: 0}`. The system prompt states the
  move-only task and the exact reply shape (see the response
  contract). Per request context appended after it: the current month
  (`YYYY-MM`), the registered deal names with their expected months,
  and the month-name tables (Portuguese and English) with the Q5
  next-occurrence rule.
- Response contract: exactly one JSON object and nothing else,
  either `{"deal": "...", "payment": "...", "target_month":
  "YYYY-MM"}` for a clear move or `{"question": "..."}` with one
  focused question when the sentence is ambiguous or names something
  unknown. `payment` is always `part-1` in this phase.
- Enforcement ladder, in order: transport or HTTP failure raises
  `ModelError` (401/403 names the key variable); a body that is not
  JSON, not an object, or empty raises `ModelError`; `plan_nl_move`
  maps any `interpret` exception to an error outcome, a non-dict
  answer to an error, a well-formed question dict to a question, and
  only then validates the move shape (T2). The page renders errors
  and questions in the page language; both leave stored data
  untouched.

Options considered: (a) free-text answers parsed with heuristics;
(b) the strict one-JSON-object contract above. Chosen (b): a
machine-checkable shape turns model drift into a visible error
instead of a silent wrong move, and the reader already strips code
fences before parsing.

### T3a. Lenient matching per Q4

Decision: two layers. The model resolves wording to a registered name
using the candidate list in its context. Before calling
`move_payment`, the app applies a deterministic fallback that
compares normalized names: Unicode NFKD decomposition with combining
marks stripped, then casefold, via the standard library
`unicodedata`. A sentence resolving to exactly one registered deal
moves it; zero matches ask naming the registered deals; two matches
ask one question naming both full names with their expected months
(Q4), and nothing moves.

Options considered: (a) prompt-only resolution; (b) deterministic
normalization fallback in addition to the prompt; (c) substring or
fuzzy scoring. Chosen (b): the prompt handles phrasing, while the
fallback makes case and accent behaviour deterministic and testable
without the network; (c) risks scoring the wrong deal as closest on
stage.

### T3b. Bare month names per Q5

Decision: a small pure helper resolves a month reference to `YYYY-MM`
or returns unknown: full month names in Portuguese and English map to
an index; a bare month name (no year) means its next occurrence from
the current month (same year when its index is at or after the
current month index, otherwise next year); an explicit `YYYY-MM`
passes through only when it matches the engine month shape. The model
is asked to return `YYYY-MM`; the helper is the testable statement
of the Q5 rule and the fallback when the model echoes a bare name.

Options considered: (a) model-only resolution with the current month
in context; (b) model plus the deterministic helper. Chosen (b), for
the same reason as T3a: the rule is pinned by tests with no network.

## T4. The example-loading action per Q1

Decision: a visible `Carregar exemplo / Load example` action on the
forecast and move pages posts (with CSRF) to a dedicated route that
first shows a confirm page warning that example settings replace the
current settings, then on confirmation:

- writes the example settings row (share 50, IVA 23, withholding 25,
  IRS reserve 30, Social Security reserve 10, monthly expenses 350.00
  in the page locale format);
- inserts two example deals with fixed idempotency keys so pressing
  the action twice creates nothing twice (the existing unique-key
  behaviour in `store.insert_deal` already returns the existing row):
  `Exemplo Lisboa`, share basis 5 000.00, expected next month, and
  `Exemplo Porto`, share basis 3 200.00, expected the month after,
  both confirmed stage, months derived from the live current month
  (T7) so the demo never rots into the past;
- redirects to the forecast page showing both deals.

The sentence hint on the move page then names the first example deal
with a bare month word, which doubles as a copy-paste input through
the Q5 rule.

Options considered: (a) always overwrite settings silently; (b) only
fill settings when none exist; (c) confirm page, then apply, deals
idempotent by key. Chosen (c): (a) silently changes a visitor's real
figures; (b) makes the button look broken on a used device; (c) asks
once and is safe to press twice. Fixed example months were rejected:
`move_payment` refuses past targets, so fixed months would
eventually break the demo without anyone changing code.

Per Q3, the fixed worked example (`MOVE_EXAMPLE_*` constants,
`move_example_result`, `move_example_page` in `app/web.py`) is
removed: example data comes only from the Q1 action.

## T5. The no-deals move page per D3/D4

Decision: with no registered deals, `GET /scenarios/move` shows the
sentence form plus a notice stating there are no deals yet, with two
links: New deal (`Novo negócio`) and the Q1 example action. Posting a
sentence with no deals yields one focused question inviting the
visitor to register a deal or load the example, and the model is
never called for an empty sentence (existing behaviour kept).

Options considered: (a) hide the scenario page until the first deal;
(b) keep the page with the notice and both links. Chosen (b): a
first-time visitor sees the headline capability, and the two links
recover the demo in one click each.

## T6. CSS approach

Decision: extend the existing `app/static/style.css` only: plain CSS,
no external assets, no web fonts, no JavaScript framework (no page
script exists today and none is added). Add a viewport meta tag to
the page shell; keep the single-column fluid layout with its current
maximum width; make inputs, selects and buttons full-width with a
comfortable touch size; keep the existing `.notice` and `.error`
patterns for questions and errors; keep `Content-Security-Policy:
default-src 'self'`, which already permits this approach with
nothing to relax.

Options considered: (a) an external CSS framework or fonts; (b) grow
the existing stylesheet. Chosen (b): (a) adds network dependencies
and CSP exceptions for a three-screen demo, while the current
stylesheet already renders every screen; consistency with the public
site's look is approximated with system type and generous spacing.

Not verified: the visual likeness to propware.pt. Fetching the public
site to compare was not possible from the build environment, so Build
matches its general character (plain, single column, system type)
rather than any measured value, and this likeness is not claimed as
tested.

## T7. Current-month source (supports Q5)

Decision: the app resolves the current month from the server date in
the Europe/Lisbon timezone via the standard library (`zoneinfo`,
falling back to UTC when timezone data is absent), keeping the
`APP_NL_CURRENT_MONTH` environment override for tests and deploy
pinning. The engine stays clock-free: the month is passed in, and
purity is unchanged.

Options considered: (a) keep the fixed `"2026-11"` default forever;
(b) server date with an environment override. Chosen (b): (a) makes
Q5 answers wrong as soon as the real month moves on, while (b) keeps
tests deterministic through the override already read by
`nl_current_month`.

## T8. Test plan: tests first, no network calls

Decision: Build writes the tests before the behaviour, following the
existing patterns, and no test touches the network:

- Engine suite: normalization helper cases (case, accents,
  non-matching names); Q5 resolution cases (bare name forward and
  wraparound, explicit `YYYY-MM` passthrough, unknown text); two-deal
  normalization producing the both-named question; records-unchanged
  snapshots; the existing fake-`interpret` style is kept, and the
  live client is never instantiated in tests.
- App suite: Q1 action confirm flow, settings replacement, deal
  idempotency on double press, CSRF refusal, markup escaping; the
  no-deals move page showing the notice with both links; posting with
  no deals asking without calling the model (patched `nl_client`
  asserting zero calls); removal of the fixed example asserted by the
  absence of its deal name and fixed months on a fresh database.
- Both proof suites (`engine/tests`, `app/tests`) stay green
  throughout; any new i18n key is added in both languages, since a
  missing key raises.

Options considered: (a) live-model integration tests; (b) fakes and
patched clients only. Chosen (b): the demo must be verifiable
offline, and the fakes already prove the no-guess rules.

## T9. `deploy/smoke.py` creates its own deal first

Decision: extend the smoke script so it seeds through the real pages
before asserting the scenario: load the move page for a CSRF token,
save example settings, register one Benfica deal via the review and
confirm forms (following the 303 redirect), then post `Move the
Benfica payment to January` and assert the before/after months
derived from the created deal's month and the Q5-resolved target.
Expected strings stay language-aware as today (numeric `YYYY-MM` or
the localized month names). Seeding failures report as their own
named check and exit non-zero.

Options considered: (a) expect preloaded data on the deployment;
(b) the script creates its own deal over HTTP. Chosen (b): the check
then proves the real visitor path end to end and never depends on
whatever data a deployment happens to hold.

## Risks

- A deployment without a model key turns every sentence into the
  configured error; the demo still loads and the Q1 deals still
  register, but no move previews. Mitigation: the smoke script's
  move check fails loudly in that case.
- The model may return a deal name that matches nothing after
  normalization; that ends as a question by design, which is safe
  but can look evasive on stage. Mitigation: the candidate list in
  the prompt context.
- Two example deals could normalize identically in a future rename;
  the result is a question, not a wrong move, by T3a.
- The Q1 confirm page replaces settings; a visitor with real data
  who confirms loses their rates. Accepted and disclosed on the
  confirm page itself; deals are only added, never removed.
- Timezone data missing on a minimal host falls back to UTC for the
  current month, which can differ from Lisbon near month
  boundaries. Accepted; the environment override covers pinned
  deployments.
- Propware.pt visual consistency was not verified (see T6); the CSS
  work follows its general character only.

## What was not verified

- The rendered look of propware.pt (fetching it failed from this
  environment).
- Live behaviour of the interpretation model against the new prompt
  context; the contract is enforced by shape checks, not by a live
  call, and no live call was made.
- Deployment specifics (host timezone data, model key presence);
  these are runtime conditions the smoke script reports on.

## Traceability to the plan criteria

- Write this file: this document.
- Update the functional doc: the companion change to
  `18-demo-ready-functional.md`.
- How the move reads registered deals: T1.
- Interface between the interpretation and `engine.move.move_payment`:
  T2.
- Prompt and response contract with the model, and error handling:
  T3 with T3a and T3b.
- Example-loading action: T4.
- CSS approach: T6.
- Test plan, tests first, no network calls: T8.
- `deploy/smoke.py` creating its own deal first: T9.
- Risks: Risks and What was not verified above.
- Options and reasons per decision: recorded under each decision.
