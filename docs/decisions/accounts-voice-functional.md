# Accounts and voice or text deal updates: functional decisions

Status: discovery draft revised against the owner's answers to all
seven open questions (received on the request page). No open
questions remain. This document now states the final functional
behaviour and is submitted for assessment and owner approval. No
design and no build follow until the owner approves this discovery
result.

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
end. The owner's answers A1-A7 below are applied as stated.
Anything not verifiable in these sources is marked as an
assumption. Nothing below was guessed.

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
Portuguese, with English available on equal terms from day one.
Stakeholders: the agent (the only product user); the
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
  agent's share percentage, escritura date (day, month, year) from
  which the forecast month derives, stage, optional CPCV date once
  signed, optional agency. One payment part by default.
- CPCV: the promissory purchase-and-sale contract whose signing
  confirms a deal in Portuguese practice. The signing date is
  recorded on the deal and shown on the deal card.
- Escritura: the final deed; its date is a full calendar date, and
  the forecast month is derived from it.
- Caidos: deals that fell through, shown in a separate collapsed
  list, excluded from the forecast, reopenable by the agent.
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
the first deal, plus one line suggesting the agent can record a
voice note for that first deal. The guided first deal keeps the
existing proven order and changes nothing stored outside the
agent's own records: empty state, settings when missing (the
existing refusal with its prompt), deal form, review, confirm,
forecast.

Options considered: (a) a dedicated onboarding wizard sequence;
(b) the existing path with empty-state guidance plus the voice-note
line. Chosen (b) per the owner's answer A4: the path is tested,
completes inside the domain brief's acceptance bound, and a wizard
adds states the pilot has not asked for. The one-line suggestion
keeps the voice path discoverable from the very first visit
without adding a screen.

## D2. Portuguese first, English on equal terms, PropWare styling

Decision: the existing language mechanism is kept unchanged.
Portuguese (pt-PT) is the default and the first language; English
is available through the same switcher. New strings follow the
existing rule: identical keys in both languages, missing keys fail
loudly, fiscal terms stay in Portuguese in English. The PropWare
styling is kept; the product stays a responsive web app with no
native app. Per the owner's answer A7, English and Portuguese are
handled the same from day one for voice input and for typed text:
transcription, extraction, the one-question flow, and the
confirmation card all work in either language, and the test suites
cover both languages for both input paths.

Options considered: (a) translate fiscal terms into English for the
English page; (b) keep them in Portuguese in both languages.
Chosen (b), as today: the terms name Portuguese obligations, and
translating them risks implying a different fiscal meaning.
Options for launch languages: (a) Portuguese voice with English
typed only; (b) both languages for both paths from day one.
Chosen (b) per the owner's answer A7: an agent who thinks in
English must get the same behaviour, and testing both paths in
both languages keeps one suite honest instead of two tiers of
quality.

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

"Delete my account" removes all of the agent's data immediately
and irreversibly: settings, deals, receipts, transcripts, and
sessions. Because there is no recovery, the action sits behind a
confirmation in which the agent types their own email address; the
deletion runs only when the typed address matches the account's.
Per the owner's answer A6 there is no grace period and no
recovery path.

Every stored row carries its tenant, and every read and write is
scoped by it. The test suites prove that one agent cannot read or
change another agent's deals, notes, or settings, including by
guessing identifiers.

Options considered: (a) passwords with reset emails; (b) email
links only. Chosen (b) per the binding owner decision: agents work
mostly on the phone, and a link removes password friction and
password storage entirely, at the cost of dependence on email
delivery, which the relay already provides. Options for deletion:
(a) immediate irreversible removal behind a typed-email
confirmation; (b) a grace period with recovery. Chosen (a) per
the owner's answer A6: the agent owns the data outright, and a
grace period would keep records the agent asked to destroy.

## D4. What each supported update means on the record

Decision (final mapping, per the owner's answers A1, A2, A3, A5):
the update box accepts five kinds of change, each resolving to the
existing record model, never to a new money rule:

- New deal: creates a deal with the current deal fields (name,
  agency commission excluding IVA, own share, escritura date,
  stage). Fields not stated are asked, never guessed.
- CPCV signed: records the CPCV signing date on the named deal,
  shows that date on the deal card, and moves the deal to
  confirmed. The date is part of the deal record, not a note.
- Escritura date set or moved: sets or moves the named deal's
  escritura date as a full calendar date (day, month, year). The
  forecast month is derived from that date, so moving the date
  moves the deal across forecast months with no separate month
  field to disagree.
- Deal fell through: moves the named deal into the Caidos list.
  Caidos deals are excluded from the forecast, shown as a separate
  collapsed list so they never clutter the working view, and
  reopenable: reopening returns the deal to the forecast at its
  stored values.
- Commission received: records the receipt with the real amount
  and date on explicit confirmation, freezing the figures exactly
  as the domain brief's receipt rule states. The receipt assistant
  is unchanged: it prepares the return fields, the agent issues on
  the Portal das Financas and records the issue, and the product
  issues nothing and touches no portal.

Options considered for fell-through deals: (a) a separate
collapsed list excluded from the forecast and reopenable; (b)
silent deletion of the deal. Chosen (a) per the owner's answer
A3: the domain brief requires states to produce separate pictures
rather than false precision, a collapsed list keeps the working
view clean, and keeping the record preserves the history the
agent may need at year end while reopening covers the deal that
comes back to life. Options for escritura: (a) reuse the expected
month; (b) a distinct date field with the month derived from it.
Chosen (b) per the owner's answer A2: one date field means the
card and the forecast can never disagree about when the money
moves.

## D5. The update box and the confirmation gate

Decision: one box on the main page. The agent records a voice note
in the browser or types text in either language; typed input stays
fully available, so a missing microphone or a noisy street never
blocks the update. Speech becomes text through Meta transcription
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
with the twelve-month history behind it. Two readings are fixed
by the owner's answers: a deal's forecast month is derived from
its escritura date (A2), and Caidos deals contribute nothing to
any scenario until reopened (A3).

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
   agent's own figures through the guided first deal; the empty
   page carries the line suggesting a voice note for the first
   deal.
2. Without a valid session nothing is visible; an expired, used,
   or guessed link and a guessed cross-tenant identifier yield no
   data and change nothing.
3. Links are single use, valid 15 minutes, stored hashed, and
   rate-limited; the mail tests prove no message ever leaves the
   test run.
4. A session survives 30 days of visits; sign-out ends only that
   device's session.
5. Deleting the account runs only when the typed address matches,
   then leaves no row of any kind for the tenant, with no
   recovery.
6. Each of the five updates completes from voice and from text
   only after Confirm; before Confirm nothing stored changes.
7. Ambiguous input produces a question and no stored change;
   transcription or model failure produces an error with the
   manual path open.
8. No audio file survives transcription; the transcript and the
   confirmed change do.
9. Forecast euros equal an engine-only computation on the
   confirmed fields; model output never enters the money path.
10. A CPCV update records the signing date, shows it on the deal
    card, and leaves the deal confirmed.
11. An escritura update stores a full calendar date and the
    forecast month follows it; moving the date moves the deal
    across months.
12. Fallen-through deals sit in a separate collapsed list,
    contribute nothing to the forecast, and return to it on
    reopening.
13. Voice and typed updates behave the same in English and in
    Portuguese; the suites cover both languages on both paths.
14. Both proof suites stay green throughout.

## Owner answers applied

The seven open questions are closed by the owner's answers on the
request page, applied above:

- A1. CPCV signed: record the CPCV date, show it on the deal
  card, and move the deal to confirmed. Applied in Terminology
  and D4, checked by criterion 10.
- A2. Escritura date: its own date (day, month, year); the
  forecast month derives from it. Applied in Terminology, D4 and
  D6, checked by criterion 11.
- A3. Deals that fell through: a separate collapsed Caidos list,
  excluded from the forecast, reopenable. Applied in Terminology,
  D4 and D6, checked by criterion 12.
- A4. Guided first deal: the existing order is enough, plus one
  line on the empty page suggesting a voice note for the first
  deal. Applied in D1, checked by criterion 1.
- A5. Commission received: confirmed as written. Applied in D4
  with the receipt assistant unchanged.
- A6. Delete my account: immediate and irreversible, behind a
  confirmation where the agent types their email. Applied in D3,
  checked by criterion 5.
- A7. English and Portuguese handled the same from day one, for
  voice and for typed text; tests cover both languages. Applied
  in D2 and D5, checked by criterion 13.

## Traceability to the request

- Real app, no mock data, guided first deal: D1, A4, criterion 1.
- Portuguese first, English available, PropWare styling: D2, A7.
- One agent per tenant, no shared views: D3, criterion 2.
- Email-link sign-up and sign-in in one flow: D3.
- Link token, hash, single use, 15 minutes, rate limits: D3,
  criterion 3.
- 30-day session, secure HTTP-only cookie, per-device sign-out:
  D3, criterion 4.
- Relay mail, environment settings, no mail in tests: D3,
  criterion 3.
- Delete-my-account removes everything: D3, A6, criterion 5.
- Tenant on every row, scoped queries, guessing-proof tests: D3,
  criterion 2.
- One box, voice or text, on the main page: D5, priorities.
- Five supported updates: D4, A1, A2, A3, A5, criterion 6.
- Transcription plus Muse extraction, one question not a guess:
  D5, criterion 7.
- Editable confirmation card with before/after, nothing without
  Confirm: D5, criterion 6.
- Audio deleted, transcript and change kept: D5, criterion 8.
- Every euro from the deterministic engine: D5, D6, criterion 9.
- CPCV date recorded, shown, confirmed: D4, A1, criterion 10.
- Escritura date with derived forecast month: D4, D6, A2,
  criterion 11.
- Caidos list, collapsed, excluded, reopenable: D4, D6, A3,
  criterion 12.
- Both languages on both input paths with tests: D2, D5, A7,
  criterion 13.
- Standard library only, no external page assets: scope note,
  carried into design.
- Tests first, stubbed network, the two proof suites: criteria 3
  and 14.
- Accounts and isolation before voice and text: priorities.
- Options and reasons per decision: recorded under each decision.
- Owner answers: A1-A7 above; no open questions remain.
