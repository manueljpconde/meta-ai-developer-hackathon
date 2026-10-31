# Accounts and voice or text deal updates: technical decisions

Status: design for owner approval. No build follows until approved.
Scope: how the approved functional behaviour is implemented; product code
is untouched by this document.

Sources: verified against the code and tests on the target branch
(`app/web.py`, `app/i18n.py`, `app/store.py`, `app/server.py`,
`engine/calc.py`, `engine/move.py`, `engine/nl_move.py`,
`engine/model_client.py`, and the suites under `app/tests/` and
`engine/tests/`), the domain brief `docs/mvp-analysis.md` (revision
of 4 October 2026), `docs/decisions/18-demo-ready-technical.md` (whose
T4/T5 demo behaviour this document retires), and the published
discovery functional decisions
`docs/decisions/accounts-voice-functional.md` (D1-D7, answers A1-A7,
criteria 1-14). Anything not verifiable there is marked as an
assumption or as not verified. Nothing below was guessed.

Binding owner amendments applied (request page): (1) AI cost guard of
at most 30 updates per tenant per day, voice notes up to 60 s, cap
message in the page language; (2) existing live data (Deal Name 1 and
the demo settings) is dropped when accounts go live and the first real
account starts empty; (3) the session lasts 30 days from sign-in, not
sliding; (4) the sign-in email uses the page language at the time of
the request; (5) accounts and isolation are built before voice and
text updates.

Binding request constraints carried in: Python standard library only,
no external scripts or assets in pages; mail via the existing relay
over TLS with the standard library client, settings from the app's
environment file, tests never sending mail; tests first with stubbed
model, transcription and mail and no network calls in tests.

## T1. Storage and the tenant model

Decision: keep the single SQLite file and add the tenant as the root
of every row. A new `tenants` table holds one row per agent (account
email, creation time). Every stored row in `settings`, `deals`, and
the new tables from T2/T6 carries its tenant id, and every read and
write is scoped by it in SQL (`WHERE tenant = ?` on each statement),
never by filtering in Python after the fact. Foreign keys reference
the tenant with cascade delete so "Delete my account" (T2) removes
all of that agent's data in one transaction.

The deals table gains columns rather than a new deal store: CPCV
signing date (nullable date), escritura date (full calendar date,
replacing the stored month), and fallen-through state for the Caidos
list (see T8). Existing single-row settings become one row per
tenant. New tables: login links (token hash, tenant email, expiry,
used flag), sessions (T2), daily update counters (T7), and update
transcripts with their confirmed changes (T6).

When accounts go live, the existing live rows (Deal Name 1 and the
demo settings) are dropped by the migration, per amendment (2); the
migration is a one-way delete of unowned rows, and the first real
account starts empty (D1). No per-tenant schema variants and no
shared-view queries exist anywhere.

Options considered: (a) one database file per tenant; (b) one shared
file with a tenant column on every row. Chosen (b): the deployment is
a single box, the current store module already opens one file, per
file databases complicate backup and delete-account atomicity, and a
column keeps every query visibly scoped in one testable place. The
cost is discipline on every statement, which the guessing-proof tests
in T10 pin down.

## T2. Email-link sign-up and sign-in, sessions, deletion

Decision: one email-link flow for sign-up and sign-in, standard
library only. Requesting a link for an address generates a random
token (`secrets.token_urlsafe`), stores only its SHA-256 hash with a
15-minute expiry, an unused flag, the requested page language (T3),
and the request counters; the link carries the raw token once, by
mail only. Opening the link hashes the presented token, accepts it
only when the hash matches an unused unexpired row, then marks that
row used (single use) and either finds the tenant for the address or
creates it (first valid link creates the account). Tokens are random
per request; nothing is derived from the address.

Rate limiting is per email address and per IP address with small
fixed caps held in the database alongside the link rows, so limits
survive restarts; exceeding either refuses the request with an error
in the page language and sends nothing. Tests use injected timestamps
and stubbed mail, never real sends.

Sessions replace the current in-memory `SESSIONS` dict, which cannot
survive restarts or separate tenants. A session row holds a random
session id, its tenant, creation time, and a fixed expiry of creation
plus 30 days, never extended by visits (non-sliding per amendment
(3)). The cookie is `HttpOnly`, `Secure`, `Path=/`, `SameSite=Lax`
(the current `SameSite=Strict` breaks the return trip from the mail
link; Lax keeps CSRF posture with the existing per-session CSRF token
checks unchanged). Sign-out deletes that session row only, ending the
session on that device and no other. Every request resolves the tenant
from the session row or sees nothing; without a valid session no data
page renders.

"Delete my account" sits behind the typed-email confirmation page
(A6): the deletion runs only when the posted address matches the
session's account address, then deletes the tenant row with cascade
(T1) inside one transaction, clears the session cookie, and lands on
a page stating removal is complete with no recovery. No grace period,
no recovery path, per the owner's answer.

Options considered: (a) sliding sessions refreshed on each visit;
(b) fixed 30 days from sign-in. Chosen (b) per amendment (3): fixed
expiry is one timestamp comparison, needs no write per visit, and
matches what the agent was told at sign-in. Options for link state:
(a) in-memory; (b) database rows. Chosen (b): links must survive
restarts and be provably single use under concurrent opens, which a
dict cannot guarantee.

## T3. Mail sending and the page-language email

Decision: send through the existing relay with the standard library
` smtplib` client only: STARTTLS against the relay host, sender
`hello@propware.pt`, message built with `email.message` as plain
text with both language bodies selected at send time. The relay host,
sender, credentials, and environment selection come from the app's
environment file, read once at startup; tests never construct the
live client and assert against a stub outbox instead.

The sign-in mail uses the page language recorded with the link
request (amendment (4)): subject, body, and expiry note render in
that language from the existing `app/i18n.py` mechanism, with the new
keys added in both languages (missing keys already fail loudly, which
stays the guard). The link URL carries the raw token as a single
query parameter; the token never appears in logs.

Options considered: (a) always send in Portuguese; (b) use the page
language at request time. Chosen (b) per amendment (4): the agent may
request the link from the English page and must be able to read what
arrives. No HTML mail and no tracking pixels: plain text keeps the
relay behaviour predictable and the tests exact.

## T4. Removing the demo behaviour

Decision: delete, not hide. The example-loading action and its
confirm page (`/example` routes, `example_action`,
`example_confirm_page`, `apply_example_data`, the `example-*`
idempotency keys and i18n keys), the two example deals and example
settings writers, the fixed worked move example constants and page,
and the whole typed move scenario page (`/scenarios/move` routes,
`nl_*` page keys kept only where the update box reuses their
wording) are removed with their tests. The navigation drops the
scenario entry; the empty forecast state gains the link to register
the first deal plus the one line suggesting a voice note for that
first deal (A4), reusing the existing notice pattern.

Removal happens in the accounts-first build step (T11) together with
the live-data drop (T1, amendment (2)), so no intermediate state can
show one agent another agent's demo rows. The smoke script's seeding
through the example action is rewritten to seed through the real
registration path.

Options considered: (a) keep the routes hidden behind a flag; (b)
full deletion. Chosen (b) per the binding request decision: dead
routes behind flags are still reachable code holding demo data
writers, and the isolation tests must be able to assert no demo path
exists.

## T5. The update box: voice and typed input

Decision: one box on the main page with two inputs feeding one
pipeline: a browser-recorded audio upload and a text field, both in
either language (A7). No external scripts or assets: recording uses
the browser's built-in recorder with a plain form upload; the 60 s
cap (amendment (1)) is hinted in the page and enforced on the server
by refusing audio over the cap with a message in the page language
before any transcription call. Typed input stays fully available, so
a missing microphone never blocks the update (D5).

Request size limits stay in the existing style (`MAX_BODY_BYTES`
grown only as far as a 60 s compressed note needs, plus the text
path unchanged), parsed with the standard library multipart handling;
oversize or undecodable bodies are refused with an error and nothing
stored changes. Audio is written to a temporary file scoped to the
request and unlinked immediately after transcription succeeds or
fails (T6); audio never lands in the database and never survives the
request.

Options considered: (a) client-side duration check only; (b) server
enforcement with a page hint. Chosen (b): client hints differ by
browser and cannot be trusted for cost control; the server refusal is
the testable guard, the hint is courtesy.

## T6. Transcription, extraction, the one question, confirmation

Decision: extend the existing `engine/model_client.py` pattern, which
already pins model `muse-spark-1.3`, standard library `urllib`,
temperature 0, and key-from-environment. Two clients behind small
interfaces so tests stub both: a transcription client sending the 60 s
audio to `muse-voice-transcribe-1.0` and returning text, and an
extraction client (a Muse model) turning text, typed or transcribed,
into exactly one JSON object and nothing else: either a structured
update for one of the five D4 kinds (named deal, explicit fields,
nothing for what was not stated) or `{"question": "..."}` with one
focused question. The enforcement ladder of T3 in the #18 design is
kept: transport or HTTP failure raises `ModelError`; non-JSON,
non-object, or empty answers raise; the planner maps exceptions to an
error outcome, well-formed questions to the one-question flow, and
validates the update shape before any engine call.

Ambiguity handling follows D5 strictly: one question at a time, each
answer reinterpreted, the extracted fields always directly editable,
and failure (transcription or model) rendered as an error with the
typed and manual form path open, never as a guess. The confirmation
card shows the editable extracted fields with the forecast before and
after, both computed by `engine.calc` on the proposed values; Confirm
saves through the normal deal-writing path with the existing
idempotency keys, so double submission saves once. Before Confirm,
nothing stored changes. The transcript and the confirmed change are
stored with the deal's history; the audio file is already gone (T5).

The five D4 mappings resolve to the existing record model only: new
deal through the guided order; CPCV date recorded on the deal with
confirmed stage; escritura date set or moved as a full date; fell
through moving the deal to Caidos; commission received recording the
receipt with frozen figures. Model output never enters the money path
(T8).

Options considered: (a) save on send with undo; (b) confirm before
saving. Chosen (b), unchanged from discovery D5: money records need
an explicit human decision, and the before/after card is where the
agent sees what an update earns. Options for extraction retries: (a)
retry ambiguities silently; (b) one question to the agent. Chosen
(b): retries spend budget hiding the ambiguity the agent must
resolve.

## T7. The AI cost guard

Decision: a per-tenant daily counter table (`tenant`, `day`, `count`)
checked before any transcription or extraction call. At most 30
updates per tenant per calendar day (Europe/Lisbon, same source as
the current-month helper); the 31st and later attempts that day are
refused with a clear message in the page language and no model call
is made. Voice notes over 60 s are refused before transcription (T5)
with the page-language message. Both refusals leave stored data
untouched and keep the typed/manual path visible for non-AI work;
they gate model spending, not record keeping. The day boundary uses
the server date source already chosen for the forecast month.

Options considered: (a) per-session counters; (b) per-tenant daily
counters. Chosen (b) per amendment (1): the cap is per tenant per
day, a session counter resets the budget on every device, and the
table survives restarts.

## T8. Money boundary and record semantics

Decision: every euro on every screen, including the confirmation
card's before/after figures, comes from `engine.calc` on confirmed
fields: integer cents, exact decimal rates, half-up rounding per
component, rates frozen at confirmation time. The transcription and
extraction outputs are strings and dates only; they are never passed
to the money functions and no money type accepts them. This is
asserted structurally (the planner's return type carries no amount
fields for the model to fill) and by tests comparing card figures
against direct engine calls.

Record semantics fixed by A1-A3: the escritura date column is the
single date field and the forecast month derives from it
(`YYYY-MM`); no separate month field may disagree. CPCV signing date
is a nullable date column shown on the deal card; setting it moves
the deal to confirmed. Fallen-through is a state on the deal,
excluded from every forecast scenario query until reopened, rendered
as the separate collapsed list. `received` stays derived, never
marked by hand. The forecast keeps its current shape: current month
plus eleven following, twelve-month history behind, four labelled
figures with the fiscal breakdown.

Options considered: (a) keep a stored month column beside the
escritura date; (b) derive the month from the date. Chosen (b) per
answer A2: two fields holding the same fact disagree on stage, one
field cannot.

## T9. Language handling for the new flows

Decision: the existing `app/i18n.py` mechanism is kept unchanged:
browser detection with the visible switcher, identical keys in both
languages enforced loudly, fiscal terms kept in Portuguese in
English, amounts and month names following the page language. Every
new string (link flow, session errors, deletion confirm, update box,
question flow, confirmation card, cap messages, empty-state line) is
added with both keys from the start; transcription, extraction, the
one-question flow, and the confirmation card work in either language
(A7), and the suites cover both languages on both input paths.

Options considered: (a) Portuguese flows first with English to
follow; (b) both languages on both paths from day one. Chosen (b)
per answer A7: one suite covering both paths in both languages keeps
a single quality bar.

## T10. Test plan: tests first, no network calls

Decision: build writes the tests before the behaviour, following the
existing suite patterns, and no test touches the network:

- Accounts suite: link request creates the pending row with hashed
  token and 15-minute expiry; opening with the raw token signs in,
  reuse and expiry and guessed tokens yield nothing; rate limits per
  email and per IP refuse without sending; first valid link for an
  unknown address creates the tenant; no valid session renders no
  data; sessions expire exactly 30 days after creation with visits
  not extending them; sign-out ends only that device's session;
  typed-email deletion removes every row of the tenant with no
  recovery, and mismatched typed addresses delete nothing; mail
  assertions run against the stub outbox.
- Isolation suite: one agent cannot read or change another agent's
  deals, notes, or settings, including by guessing identifiers in
  URLs and form fields; every cross-tenant access test asserts both
  no data and no change.
- Update suite: each of the five D4 kinds completes from voice bytes
  and from text only after Confirm, with before-Confirm snapshots
  proving nothing stored changed; ambiguity yields the question and
  no change; transcription or model failure yields the error with the
  manual path open; audio file absence after the request is
  asserted; card figures equal direct engine calls; both languages
  on both paths.
- Guard suite: the 31st update of the day is refused without a model
  call (stub counts calls); over-60 s audio is refused without a
  transcription call; both messages render in the page language.
- Both proof suites (`engine/tests`, `app/tests`) stay green
  throughout; any new i18n key exists in both languages.

Options considered: (a) live-model integration tests; (b) fakes and
patched clients only. Chosen (b): verification must run offline, and
the fakes already prove the no-guess rules.

## T11. Build order and deploy notes

Decision: build order follows amendment (5): accounts and isolation
with the demo removal and live-data drop first (T1-T4, T8 record
changes, T10 accounts and isolation suites), then voice and text
updates with the guards (T5-T7, T9-T10 remainder). The product stays
a responsive web app on the single box with the PropWare styling
extended in `app/static/style.css` only, no external assets, keeping
the current content-security posture. Environment-driven settings
(mail relay, model keys, month override for tests) are read from the
app's environment file; a missing model key turns update attempts
into the configured error while every non-AI page keeps working, and
the deploy check reports that state by name.

Options considered: (a) build voice first to show the headline
feature; (b) accounts and isolation first. Chosen (b) per amendment
(5): without isolation there is no safe user to demo voice to, and
the deadline favours landing the foundation that cannot slip.

## Risks

- Email deliverability decides sign-in: relay misconfiguration or
  spam filtering locks agents out with no fallback login. Mitigation:
  the deploy check sends nothing but verifies relay settings load,
  and the error page names the expiry and the retry path.
- Concurrent link opens could double-create a tenant or double-use a
  link. Mitigation: unique constraints on the token hash and the
  tenant email with the used-flag update inside one transaction.
- SQLite concurrent writes under two devices at once can meet a
  busy database. Accepted: the app's write volume is one agent's
  clicks; writes stay in short transactions and retries are bounded.
- Model output drift (new fields, prose around the JSON) ends as a
  visible error by the shape checks, which is safe but can read as
  evasive mid-demo. Mitigation: the prompt context names the deal
  candidates and the strict one-object contract.
- Two deals normalizing identically still resolve to a question, not
  a wrong deal, by the deterministic name matching kept from the
  #18 design.
- Timezone data missing on a minimal host falls back to UTC for the
  current month and the daily cap boundary. Accepted; the
  environment override covers pinned deployments.
- A visitor with bookmarks to removed demo routes meets errors.
  Accepted and intended: the routes are gone, and the empty state
  points at the real first deal.

## What was not verified

- Live behaviour of the transcription and extraction models against
  the new prompt context; the contracts are enforced by shape
  checks, not by a live call, and no live call was made.
- Live delivery through the relay; sending is stubbed in tests and
  only settings loading is verified locally.
- Relay rate behaviour under burst link requests beyond the app's
  own per-email and per-IP caps.
- The rendered likeness to the PropWare styling beyond the current
  stylesheet's general character.
- Deployment specifics (host timezone data, relay credentials, model
  key presence); these are runtime conditions the deploy check
  reports on.

## Technical acceptance criteria

Each criterion is checked against the built product with stubbed
transcription, model, and mail, with no network calls in tests:

1. Without a valid session no data page renders; an expired, used,
   or guessed link and a guessed cross-tenant identifier yield no
   data and change nothing.
2. Link rows store hashes, never raw tokens; links are single use
   and valid 15 minutes; rate limits per email and per IP refuse
   without sending; the mail tests prove no message ever leaves the
   test run.
3. A session expires exactly 30 days after sign-in regardless of
   visits; sign-out ends only that device's session.
4. Deleting the account runs only when the typed address matches,
   then leaves no row of any kind for the tenant, with no recovery.
5. Going live drops the existing demo rows; a new account starts
   empty and reaches a forecast through the guided first deal, with
   the voice-note line on the empty page and no demo route
   reachable.
6. Each of the five updates completes from voice and from text only
   after Confirm; before Confirm nothing stored changes.
7. Ambiguous input produces one question and no stored change;
   transcription or model failure produces an error with the manual
   path open.
8. No audio file survives the request; the transcript and the
   confirmed change do.
9. Confirmation-card euros equal an engine-only computation on the
   confirmed fields; model output never enters the money path.
10. A CPCV update records the signing date, shows it on the deal
   card, and leaves the deal confirmed.
11. An escritura update stores a full calendar date and the forecast
   month follows it; moving the date moves the deal across months.
12. Fallen-through deals sit in the separate collapsed list,
   contribute nothing to the forecast, and return to it on
   reopening.
13. The 31st update of the day and over-60 s audio are refused
   without a model call, with the message in the page language.
14. Voice and typed updates behave the same in English and in
   Portuguese; the suites cover both languages on both paths.
15. Both proof suites stay green throughout.

## Traceability to the plan criteria

- Real app, no mock data, guided first deal: T1, T4, T8, criteria
  5 and 6.
- Portuguese first, English available, PropWare styling: T9, T11.
- One agent per tenant, no shared views: T1, criterion 1.
- Email-link sign-up and sign-in in one flow: T2, criterion 2.
- Link token, hash, single use, 15 minutes, rate limits: T2,
  criterion 2.
- 30-day session, secure HTTP-only cookie, per-device sign-out: T2,
  criterion 3.
- Relay mail, environment settings, no mail in tests: T3, criterion
  2.
- Delete-my-account removes everything: T1, T2, criterion 4.
- Tenant on every row, scoped queries, guessing-proof tests: T1,
  T10, criterion 1.
- One box, voice or text, on the main page: T5.
- Five supported updates: T6, T8, criteria 6, 10, 11, 12.
- Transcription plus Muse extraction, one question not a guess: T6,
  criterion 7.
- Editable confirmation card with before/after, nothing without
  Confirm: T6, criteria 6 and 9.
- Audio deleted, transcript and change kept: T5, T6, criterion 8.
- Every euro from the deterministic engine: T8, criterion 9.
- Standard library only, no external page assets: T2, T3, T5, T6,
  T11.
- Tests first, stubbed network, the two proof suites: T10, criteria
  2 and 15.
- 30 updates per tenant per day, 60 s voice cap, page-language cap
  message: T5, T7, criterion 13.
- Live demo data dropped, first account starts empty: T1, T4,
  criterion 5.
- 30-day non-sliding session: T2, criterion 3.
- Sign-in email in the page language at request time: T3.
- Accounts and isolation before voice and text: T11.
- Options and reasons per decision: recorded under each decision.
