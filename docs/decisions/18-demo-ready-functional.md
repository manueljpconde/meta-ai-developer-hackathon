# Demo-ready functional decisions (issue #18)

Status: discovery proposal for owner approval. No design or build follows until approved.
Scope: functional behaviour of the live product demo only. Technical choices belong
to the design phase document.

Sources: verified against the live code and tests on the main branch
(`app/web.py`, `app/i18n.py`, `app/store.py`, `engine/move.py`,
`engine/nl_move.py`, `deploy/smoke.py`, and the suites under `app/tests/`
and `engine/tests/`). Anything not verifiable there is marked as an
assumption or an open owner question. Nothing below was guessed.

## D1. Agent journey from first visit to the move scenario

Decision: the demo journey keeps the existing order and changes nothing stored.

1. First visit lands on the forecast page. Language follows the browser
   (`Accept-Language` family match) with a visible switcher; the default is
   Portuguese.
2. With no settings saved, registering a deal is refused with a prompt to
   define settings first, so the agent configures share, IVA, withholding,
   IRS and Social Security reserves, and monthly expenses before any deal.
3. The agent adds a deal (name, agency commission excl. IVA, own share,
   expected month, stage), reviews the computed figures, and confirms.
   Confirming twice with the same key saves once.
4. The forecast page lists one section per month with the deal and the four
   figures (see D4).
5. The move scenario page (`/scenarios/move`) shows one sentence form plus a
   worked example. Posting a sentence returns one of three outcomes on the
   same page: a before/after forecast, one focused question, or an error.
   Nothing stored ever changes, whatever the outcome.

Options considered: (a) a guided demo mode that pre-fills settings and a
deal; (b) keeping the real registration path end to end. Chosen (b), because
the demo must prove the real product path a visitor would follow, and a
parallel demo mode would demonstrate behaviour the product does not have.

## D2. How a sentence identifies one of the agent's own deals and payments

Verified facts constraining every case below: each registered deal is read as
exactly one unpaid expected payment (`part-1` in the deal's own month);
matching inside the engine is exact on deal name and payment reference; any
refusal from the engine surfaces as one focused question, never a guess; a
model failure surfaces as an error, never a guess; an empty sentence asks
which payment and month without calling the model; an overlong sentence is
refused before any model call.

Decision: the sentence is interpreted to a registered deal name, the payment
`part-1`, and a target month; the engine match stays exact, and every
non-match becomes one focused question.

Options considered: (a) lenient matching (case-insensitive, substring) inside
the product; (b) exact engine match with interpretation resolving wording to
the registered name, questions otherwise. Chosen (b), because leniency risks
moving the wrong payment silently, while a question keeps the demo honest
about what was understood.

### D2a. Partial names

Decision: a partial name that resolves to exactly one registered deal moves
that deal; a partial name resolving to zero or to more than one deal produces
one focused question naming what is needed.

Options considered: (a) auto-complete to the closest name; (b) resolve only
unambiguous partials, ask otherwise. Chosen (b): auto-completing a partial
name can pick the wrong deal on stage, while one question recovers the demo
in a single follow-up sentence.

### D2b. Two deals that match

Decision: when the wording matches two registered deals, the product moves
nothing and asks one focused question distinguishing the candidates (for
example by full name and expected month).

Options considered: (a) move the first match; (b) move both; (c) ask one
question. Chosen (c): (a) and (b) change the forecast on an ambiguous reading,
which contradicts the rule that nothing moves on ambiguity.

### D2c. Unknown deal

Decision: a sentence naming no registered deal produces one focused question
stating the name was not found, and moves nothing.

Options considered: (a) an error message; (b) a question inviting the agent
to name a registered deal. Chosen (b), because the situation is recoverable
in the demo: the visitor simply names a deal they registered.

### D2d. Deal with no expected payments

Decision: the move scenario only ever sees unpaid expected payments; received
payments are excluded from the forecast by definition. A sentence that
matches nothing unpaid therefore ends as one focused question, and nothing
moves.

Verified fact: registered deals are currently always read as unpaid
(`received: False`), so every registered deal has expected money in this
path. Options considered: (a) track received state per deal for the demo;
(b) treat every registered deal as movable expected money and document the
limitation. Chosen (b) for this phase: adding received-state tracking is a
product change that belongs to design and build, not to demo wording. The
open question Q2 below asks the owner whether the demo needs it.

## D3. The no-deals state

Decision: with no registered deals, the forecast page shows the empty message
with a link to register the first deal; the move scenario page still shows
the sentence form and the worked example; posting a sentence with no deals
yields one focused question inviting the visitor to register a deal first,
and the model is never called for an empty sentence.

Options considered: (a) hide the scenario page until the first deal exists;
(b) keep the page visible with the worked example. Chosen (b): a first-time
visitor sees the headline capability before committing to data entry, and the
example (fixed figures, see D4) demonstrates the before/after shape with no
stored data.

## D4. What the forecast shows before and after

Decision: before and after use the same per-month shape as the forecast page:
commission, what will reach the account, money to set aside (with the
IVA / IRS / Social Security breakdown), and what is really the agent's,
with months in chronological order. The result names the moved deal with the
source and target months ("Deal, source month leading to target month"),
then the Before section computed from the current records and the After
section computed with the payment moved. Both are display only.

Options considered: (a) show only the two affected months; (b) show the full
before and after forecasts. Chosen (b): the demo story is the forecast
moving, and hiding unaffected months would conceal that nothing else changed.

The worked example keeps its fixed figures (November 2026 to December 2026,
5 000,00 commission basis) so the page is meaningful with zero registered
deals. Assumption: the example months remain in the future relative to the
demo date; Q3 asks the owner to confirm.

## D5. Portuguese and English wording

Decision: every string stays in the single per-language table with identical
keys in both languages; a missing key fails loudly rather than falling back.
Fiscal terms stay in Portuguese in English. Month names and amount formats
follow the page language (5 000,00 EUR style in Portuguese, euros 5,000.00
style in English). The sentence box accepts either language; interpretation
resolves it to the registered (Portuguese) deal name. Questions and errors
render in the page language.

Options considered: (a) translate fiscal terms into English; (b) keep them in
Portuguese in both languages. Chosen (b): the terms refer to Portuguese
obligations (IVA, IRS, Seguranca Social, withholding), and translating them
risks implying a different fiscal meaning.

The worked example sentence stays "Move the Benfica payment to January."
in both languages, as today, so the hint doubles as a copy-paste demo input.

## D6. What is out of scope

- Changing, saving, or receiving anything from a sentence; the scenario is
  display only.
- Deals with several payments, received-state tracking, or recurring
  expenses in the scenario path.
- Automatic disambiguation, persistent scenarios, or scenario history.
- New fiscal computation, tax advice, or receipt assistance.
- CRM, property, lead, banking, or Portal das Financas integrations.
- A native mobile app; the demo is the responsive web product.
- A free plan or any pricing change.
- Any change to the proof suites; both suites must stay green, proving the
  document touches nothing else.

## Open questions for the owner (not guessed)

- Q1. Should the live demo preload the example deal (or the Benfica deal the
  smoke check names) so the sentence works on first load, or must the
  visitor register a deal first?
- Q2. Must the demo show a deal with no expected payments distinctly (for
  example a received deal), or is treating every registered deal as movable
  expected money sufficient?
- Q3. Are the worked example months still suitable for the demo date, or
  should they move?
- Q4. Should partial-name matching be more lenient than D2a (for example
  ignoring case and accents), and if two deals still match, which wording
  should the question use?
- Q5. Which current month should the live scenario assume when a sentence
  names a month without a year (for example "January")?

## Traceability to the request

- Agent journey: D1.
- Sentence identifying a deal and payments, partial names, two matches,
  unknown deal, deal with no expected payments: D2 with D2a-D2d.
- No-deals state: D3.
- Forecast before and after: D4.
- Portuguese and English wording: D5.
- Out of scope: D6.
- Options and reasons per decision: recorded under each decision.
- Owner-only questions: listed above, unanswered, for the owner.
