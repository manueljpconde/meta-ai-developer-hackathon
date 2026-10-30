# Demo-ready functional decisions (issue #18)

Status: discovery proposal approved by the owner with binding amendments
Q1-Q5 and D3/D4 (recorded below); the design document
`18-demo-ready-technical.md` implements them. No build follows until
the owner approves the design.
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
   A visible "Carregar exemplo / Load example" action (amendment Q1)
   offers a shortcut: it creates example settings and two example
   deals, so the visitor can try the demo without typing figures.
3. The agent adds a deal (name, agency commission excl. IVA, own share,
   expected month, stage), reviews the computed figures, and confirms.
   Confirming twice with the same key saves once.
4. The forecast page lists one section per month with the deal and the four
   figures (see D4).
5. The move scenario page (`/scenarios/move`) shows one sentence form.
   Example data comes only from the Q1 action (amendment Q3); there is
   no fixed worked example on the page. Posting a sentence returns one
   of three outcomes on the same page: a before/after forecast, one
   focused question, or an error. Nothing stored ever changes,
   whatever the outcome.

Options considered: (a) a guided demo mode that pre-fills settings and a
deal; (b) keeping the real registration path end to end; (c) the real
path plus the Q1 example-loading shortcut. Chosen (c) per the owner's
binding amendment: the demo still proves the real product path, while
the Q1 action gives a first-time visitor working data in one step.

## D2. How a sentence identifies one of the agent's own deals and payments

Verified facts constraining every case below: each registered deal is read as
exactly one unpaid expected payment (`part-1` in the deal's own month);
any refusal from the engine surfaces as one focused question, never a
guess; a model failure surfaces as an error, never a guess; an empty
sentence asks which payment and month without calling the model; an
overlong sentence is refused before any model call.

Decision: the sentence is interpreted to a registered deal name, the payment
`part-1`, and a target month. Matching ignores case and accents
(amendment Q4): a name that resolves to exactly one registered deal
moves it; zero matches ask naming the registered deals. A month named
without a year means its next occurrence from the current month
(amendment Q5). The engine match itself stays exact, and every
non-match becomes one focused question.

Options considered: (a) exact matching only; (b) case- and
accent-insensitive matching with interpretation resolving wording to
the registered name, questions otherwise. Chosen (b) per the owner's
binding amendment: the leniency covers typing on stage, while a
question still guards every remaining ambiguity.

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
nothing and asks one focused question naming both deals with their
months (amendment Q4).

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

Decision (amendment Q2): every registered deal is treated as movable
expected money. Registered deals are read as unpaid (`received:
False`), so every registered deal has expected money in this path,
and no received-state tracking is added for the demo.

## D3. The no-deals state

Decision (amendments D3/D4): with no registered deals, the forecast page
shows the empty message with a link to register the first deal; the
move scenario page shows the sentence form plus a notice stating
there are no deals yet, with links to register a deal (New deal /
Novo negócio) and to the Q1 example action. Posting a sentence with
no deals yields one focused question inviting the visitor to register
a deal or load the example first, and the model is never called for
an empty sentence.

Options considered: (a) hide the scenario page until the first deal exists;
(b) keep the page visible with the notice and both links. Chosen (b):
a first-time visitor sees the headline capability, and either link
recovers the demo in one step.

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

The worked example is removed (amendment Q3): example data comes only
from the Q1 action, so the page carries no fixed figures and no fixed
example months.

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

The sentence hint names the first Q1 example deal with a bare month word,
so the hint doubles as a copy-paste demo input through the Q5 rule.

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

## Owner amendments Q1-Q5 and D3/D4 (answered, binding)

- Q1. Add a visible "Carregar exemplo / Load example" action that
  creates example settings and two deals. Applied in D1, D3, D4, D5;
  implemented by the design document.
- Q2. Every registered deal is movable expected money. Applied in D2d.
- Q3. No fixed worked example; example data comes only from Q1.
  Applied in D1, D3, D4, D5.
- Q4. Matching ignores case and accents; if two deals still match,
  the question names both with their months. Applied in D2 and D2b.
- Q5. A month without a year means its next occurrence from the
  current month. Applied in D2 and D5.
- D3/D4. With no deals, the move page says so and links to New deal
  and the Q1 action. Applied in D3.

## Traceability to the request

- Agent journey: D1.
- Sentence identifying a deal and payments, partial names, two matches,
  unknown deal, deal with no expected payments: D2 with D2a-D2d.
- No-deals state: D3.
- Forecast before and after: D4.
- Portuguese and English wording: D5.
- Out of scope: D6.
- Options and reasons per decision: recorded under each decision.
- Owner-only questions: answered by the binding amendments above; no open
  owner questions remain.
