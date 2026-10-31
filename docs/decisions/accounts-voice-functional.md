# Accounts and voice or text deal updates: functional decisions

Status: discovery draft for owner review. Open owner questions Q1-Q7
are posted on the request page; this document will be revised against
the owner's answers before the result is submitted for assessment and
owner approval. No design and no build follow until the owner approves
this discovery result.

Scope: functional behaviour of the real multi-agent product only:
accounts with tenant isolation, and voice or text deal updates. How
each decision is implemented (storage shape, token format,
transcription wiring, prompts, thresholds) belongs to the design
phase document. Product code is untouched by this document.

Sources: verified against the live code and tests on the main branch
(`app/web.py`, `app/i18n.py`, `app/store.py`, `app/server.py`,
`engine/calc.py`, `engine/move.py`, `engine/nl_move.py`,
`engine/model_client.py`, and the suites under `app/tests/` and
`engine/tests/`), the domain brief `docs/mvp-analysis.md` (revision
of 4 October 2026), and `docs/decisions/18-demo-ready-functional.md`
(demo behaviour this document supersedes). The owner's binding
decisions from the request are applied as stated and traced at the
end. Anything not verifiable in these sources is marked as an
assumption or an open owner question. Nothing below was guessed.

## Business problem and users

Independent real estate agents in Portugal close deals through
agencies but carry their own costs (travel, advertising, photography,
equipment) and their own fiscal obligations (IVA, withholding,
IRS and Social Security reserves). The verified domain finding is
that agents mistake the agency commission for profit and discover
too late what a deal really earned them. The product promise,
unchanged: show what the agent will receive, what to set aside, and
what is really theirs.

Target user: one independent agent, working alone, on the web, in
Portuguese. Stakeholders: the agent (the only product user); the
brokerage holding the CRM of record (no integration: manual entry
stays until proven blocking, per the domain brief); the owner's
association channel for the paid pilot (unchanged by this
document). Explicitly not users: agencies, managers, teams. There
are no shared views, no rankings, no multi-user roles in this
product.

## Terminology

- Tenant: exactly one agent and all of that agent's data. One agent
  per tenant; a tenant never sees another tenant's data.
- Deal (negocio): name, agency commission excluding IVA, the
  agent's share percentage, expected month, stage, optional agency.
  One payment part by default.
- CPCV: the promissory purchase-and-sale contract whose signing
  confirms a deal in Portuguese practice.
- Escritura: the final deed; its date is when the agent expects the
  money to move.
- The four figures, always labelled separately: commission
  (excluding IVA), what will reach the account, money to set aside
  (IVA / IRS / Social Security breakdown), and what is really the
  agent's.
- Received: a derived state, never a stage the agent marks by hand.
- Update: one voice or typed message that proposes a change to the
  agent's records. Nothing is a record before the agent confirms it.

## Verified facts constraining every decision

- Today there are no accounts. One shared database file holds all
  settings and deals; sessions are in-memory random tokens carrying
  only CSRF protection. Any device reaching the box sees and
  changes the same data.
- Deal registration already works end to end (form, review,
  confirm; confirming twice with the same key saves once) with
  frozen rates at confirmation time. Registering a deal with no
  settings saved is refused with a prompt to define settings
  first. A deal is readable as confirmed, likely or potential
  expected money; `received` is derived, not marked.
- Every euro on screen comes from `engine.calc`: integer cents,
  exact decimal rates, half-up rounding per component. The model
  never computes money today (the typed move scenario is display
  only) and must never compute it.
- Language works: browser detection with a visible switcher,
  identical keys in both languages enforced loudly, fiscal terms
  kept in Portuguese in English, amounts and month names following
  the page language.
- There is no email, audio, transcription, or extraction code.
  Login links, tenant scoping, recording, transcription, and
  structured extraction are all new.
- The demo behaviour being removed is: the example-loading action
  with its two example deals and example settings, the fixed
  worked move example, and the typed move scenario page.

## D1. Real app, no mock data, guided first deal

Decision: the example action, the example deals, the example
settings, and the fixed worked move example are removed. The typed
move scenario page is removed and replaced by the update box in D5,
which really saves after confirmation. A new account starts empty:
the forecast page shows the empty message with a link to register
the first deal. The guided first deal keeps the existing proven
order and changes nothing stored outside the agent's own records:
empty state, settings when missing (the existing refusal with its
prompt), deal form, review, confirm, forecast.

Options considered: (a) a dedicated onboarding wizard sequence;
(b) the existing path with empty-state guidance. Chosen (b) as the
proposal: the path is tested, completes inside the domain brief's
acceptance bound, and a wizard adds states the pilot has not asked
for. Q4 asks the owner to confirm this or require a wizard.

## D2. Portuguese first, PropWare styling

Decision: the existing language mechanism is kept unchanged.
Portuguese (pt-PT) is the default and the first language; English
is available through the same switcher. New strings follow the
existing rule: identical keys in both languages, missing keys fail
loudly, fiscal terms stay in Portuguese in English. The PropWare
styling is kept; the product stays a responsive web app with no
native app. Q7 asks which spoken languages voice input must serve
at launch; typed input accepts either language as today.

Options considered: (a) translate fiscal terms into English for the
English page; (b) keep them in Portuguese in both languages.
Chosen (b), as today: the terms name Portuguese obligations, and
translating them risks implying a different fiscal meaning.

## D3. Accounts and tenant isolation

Decision: one agent per tenant. No agencies, no managers, no
shared views; any multi-user reading of the data does not exist.

Sign-up and sign-in are one email-link flow: the agent enters an
email address, receives a link, and opening it signs in; the first
valid link for an unknown address creates the account. There are
no passwords and no other login method. Each link carries a random
token stored only as a hash, is single use, is valid 15 minutes,
and is rate-limited per email address and per IP address. The mail
is sent from the existing relay with sender `hello@propware.pt`;
settings come from the app's environment file; tests never send
email. A session lasts 30 days in a secure HTTP-only cookie, and
sign-out ends the session on that device.

"Delete my account" removes all of the agent's data: settings,
deals, receipts, transcripts, and sessions. Q6 asks whether
deletion is immediate or keeps a grace period.

Every stored row carries its tenant, and every read and write is
scoped by it. The test suites prove that one agent cannot read or
change another agent's deals, notes, or settings, including by
guessing identifiers.

Options considered: (a) passwords with reset emails; (b) email
links only. Chosen (b) per the binding owner decision: agents work
mostly on the phone, and a link removes password friction and
password storage entirely, at the cost of dependence on email
delivery, which the relay already provides. Options for deletion:
(a) immediate irreversible removal; (b) a grace period with
recovery. No default is proposed; Q6 asks the owner because it
decides whether a mistaken tap can destroy the business record.

## D4. What each supported update means on the record

Decision (proposed mapping, pending Q1, Q2, Q3, Q5): the update box
accepts five kinds of change, each resolving to the existing
record model, never to a new money rule:

- New deal: creates a deal with the current deal fields (name,
  agency commission excluding IVA, own share, expected month,
  stage). Fields not stated are asked, never guessed.
- CPCV signed: marks the named deal confirmed. Whether a CPCV date
  is recorded alongside, and where it is shown, is Q1.
- Escritura date set or moved: sets or moves the named deal's
  expected month. Whether the escritura date is a distinct date
  from the expected month is Q2.
- Deal fell through: records a terminal outcome on the named deal;
  its expected money leaves the forecast. How it is presented
  (separate list, history entry, or hidden) is Q3.
- Commission received: records the receipt with the real amount
  and date on explicit confirmation, freezing the figures exactly
  as the domain brief's receipt rule states. The receipt assistant
  is unchanged: it prepares the return fields, the agent issues on
  the Portal das Financas and records the issue, and the product
  issues nothing and touches no portal. Q5 confirms this reading.

Options considered for fell-through deals: (a) a new terminal
stage kept visible apart from the forecast; (b) silent deletion of
the deal. Chosen (a) as the proposal: the domain brief requires
states to produce separate pictures rather than false precision,
and a silent deletion rewrites history the agent may need at
year end. Options for escritura: (a) reuse the expected month;
(b) a distinct date field. No default is proposed; Q2 asks the
owner because it changes the deal shape the design must build.

## D5. The update box and the confirmation gate

Decision: one box on the main page. The agent records a voice note
in the browser or types text; typed input stays fully available,
so a missing microphone or a noisy street never blocks the
update. Speech becomes text through Meta transcription
(`muse-voice-transcribe-1.0`); a Muse model turns the text (or the
typed message) into the structured change, returning stated facts
only and nothing for what was not stated. When something is
missing or ambiguous, the product asks one question instead of
guessing; each answer is reinterpreted, one question at a time,
and the agent can always correct the fields directly instead of
answering.

Before anything is saved, a confirmation card shows the extracted
fields (editable) with the forecast before and after, computed by
the deterministic engine on the proposed values. Nothing is saved
without Confirm. A transcription or model failure is an error,
never a guess: the message says so, the typed and manual form
path stays open, and nothing stored changes. Audio is deleted
after transcription; the transcript and the confirmed change are
kept with the deal's history. Every euro shown comes from the
existing deterministic engine on confirmed fields; model output
never enters the money path.

Options considered: (a) save on send with undo; (b) confirm
before saving. Chosen (b): money records need an explicit human
decision, and the before/after card is the moment the agent sees
what an update really earns them. Options for ambiguity: (a) a
full correction form up front; (b) one question at a time with the
fields always editable. Chosen (b): voice is fastest when one
answer completes the update, while the editable card keeps full
control for the cases a question cannot resolve.

## D6. Forecast, scenarios, and history keep their meaning

Decision: the four figures with their breakdown, the three
scenarios (confirmed, likely, total), and the derived received
state keep exactly the meaning the domain brief and the engine
give them today. Updates flow through them; this document changes
no money rule, no rounding, and no fiscal treatment. The forecast
still covers the current month and the eleven following months
with the twelve-month history behind it.

Options considered: (a) a separate forecast presentation for
voice-entered deals; (b) one forecast whatever the entry path.
Chosen (b): the entry path must never change what a euro means,
or the agent cannot trust the comparison of forecast against
received.

## D7. What is out of scope

- Agencies, managers, teams, shared views, rankings.
- Passwords, other login methods, account recovery beyond a new
  link.
- Billing and subscription changes: the paid pilot terms stay as
  the domain brief states them, untouched by this document.
- The receipt assistant's boundary: preparation and recording
  only, no issuance, no portal access, no fiscal advice.
- New fiscal computation, official tax calculation, or receipt
  assistance beyond the assistant above.
- CRM, property, lead, banking, or Portal das Financas
  integrations.
- A native mobile app; the product is the responsive web app.
- Automatic disambiguation beyond the one-question flow, saved
  drafts of unconfirmed updates, or update history beyond the
  transcript and the confirmed change.
- Any model role in computing money.

## Business acceptance criteria

Each criterion is checked against the built product with stubbed
transcription, model, and mail, with no network calls in tests:

1. A new account starts empty and reaches a forecast from the
   agent's own figures through the guided first deal.
2. Without a valid session nothing is visible; an expired, used,
   or guessed link and a guessed cross-tenant identifier yield no
   data and change nothing.
3. Links are single use, valid 15 minutes, stored hashed, and
   rate-limited; the mail tests prove no message ever leaves the
   test run.
4. A session survives 30 days of visits; sign-out ends only that
   device's session.
5. Deleting the account leaves no row of any kind for the tenant.
6. Each of the five updates completes from voice and from text
   only after Confirm; before Confirm nothing stored changes.
7. Ambiguous input produces a question and no stored change;
   transcription or model failure produces an error with the
   manual path open.
8. No audio file survives transcription; the transcript and the
   confirmed change do.
9. Forecast euros equal an engine-only computation on the
   confirmed fields; model output never enters the money path.
10. Both proof suites stay green throughout.

## Priorities

Accounts with tenant isolation land first, then voice or text
updates, so the product is always a real app with real users
before it listens to them. Within updates, typed input lands with
the box (it is the fallback every other path depends on), then
voice, then the five update kinds in the order of D4.

## Open owner questions

- Q1. CPCV signed: is marking the deal confirmed sufficient, or
  must a CPCV date be recorded and shown (and where)? Gates the
  deal shape the design must build.
- Q2. Escritura date: is it the expected month the product
  already has, or a distinct date with its own display? Gates the
  deal shape and the forecast logic.
- Q3. Deals that fell through: shown as a separate visible list,
  kept only in history, or hidden entirely? Gates the forecast
  page design and year-end usefulness.
- Q4. Guided first deal: is the existing order (empty state,
  settings when missing, deal form, review, confirm) sufficient
  guidance, or is a dedicated onboarding sequence required?
  Gates the first-run screens.
- Q5. Commission received: confirm the reading that a receipt
  records the real amount and date with frozen figures and the
  receipt assistant unchanged. Gates the payment and receipt
  design.
- Q6. Delete my account: immediate irreversible removal, or a
  grace period with recovery? Gates the account lifecycle and
  decides whether a mistaken tap can destroy the record.
- Q7. Voice input: must it serve spoken English at launch, or is
  Portuguese sufficient with English typed? Gates the
  transcription behaviour the design must specify.

## Traceability to the request

- Real app, no mock data, guided first deal: D1, criterion 1.
- Portuguese first, English available, PropWare styling: D2.
- One agent per tenant, no shared views: D3, criterion 2.
- Email-link sign-up and sign-in in one flow: D3.
- Link token, hash, single use, 15 minutes, rate limits: D3,
  criterion 3.
- 30-day session, secure HTTP-only cookie, per-device sign-out:
  D3, criterion 4.
- Relay mail, environment settings, no mail in tests: D3,
  criterion 3.
- Delete-my-account removes everything: D3, Q6, criterion 5.
- Tenant on every row, scoped queries, guessing-proof tests: D3,
  criterion 2.
- One box, voice or text, on the main page: D5, priorities.
- Five supported updates: D4, criterion 6.
- Transcription plus Muse extraction, one question not a guess:
  D5, criterion 7.
- Editable confirmation card with before/after, nothing without
  Confirm: D5, criterion 6.
- Audio deleted, transcript and change kept: D5, criterion 8.
- Every euro from the deterministic engine: D5, D6, criterion 9.
- Standard library only, no external page assets: scope note,
  carried into design.
- Tests first, stubbed network, the two proof suites: criteria 3
  and 10.
- Accounts and isolation before voice and text: priorities.
- Options and reasons per decision: recorded under each decision.
- Owner-only questions: Q1-Q7 above, posted on the request page;
  no other open questions remain.
