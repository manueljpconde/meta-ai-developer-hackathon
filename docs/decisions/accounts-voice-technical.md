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
account starts empty; (3) the session lasts 24 hours from sign-in, not
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
plus 24 hours, never extended by visits (non-sliding per amendment
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
(b) fixed 24 hours from sign-in. Chosen (b) per amendment (3): fixed
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

## T5. The panel, the script and speech

Decision: one "Falar" button on every signed-in page opens the panel;
all behaviour lives in `app/static/voice.js`, served same-origin at
`/static/voice.js` and loaded with a script tag (the content security
policy is `default-src 'self'`, so there is no inline script and no
external script or asset). The panel is in the page markup with the
`hidden` attribute, so it is closed on load; the stylesheet only adds
`display: none` for `[hidden]`, never for the opened panel. Every text
in the panel (placeholder, Send, Cancel, Confirm, the connection and
microphone messages) is rendered from `app/i18n.py` in the page
language; the script holds no wording of its own and reads its messages
from data attributes on the panel.

The script talks to four endpoints with `format=json`: `/voice/extract`
(typed or transcribed text), `/voice/confirm`, `/voice/cancel`, and
`/voice/transcribe` (a raw `audio/wav` body, with the CSRF token and
conversation id in the query string). Every answer is one JSON object
with `state` (`ask`, `confirm`, `saved`, `cancelled`, `ended` or
`error`), `question`, `readback`, `message`, `transcript`, `understood`,
`conversation_id` and `lang`. The conversation id goes back with every
turn, so each answer continues the same conversation; the page under
the panel is not replaced, and reloads once, after a save, a cancel or
a stop. Without the script the same endpoints answer a plain page with
the same forms.

Recording uses the Web Audio API in the browser: the microphone stream
is downsampled to 16 kHz and encoded as a mono 16-bit PCM WAV in inline
JavaScript of the script itself, because browsers record webm or mp4
and the box has no ffmpeg. The server checks the WAV header (RIFF/WAVE,
PCM, mono, 16 bit, 16000 Hz) and the 60 s cap before any model call and
refuses anything else with the message in the page language; a body
larger than a 60 s WAV is refused before it is read. Audio is held in
memory for the request only: it is never written to a file or to the
database.

Speech output uses the browser's built-in `speechSynthesis`, with a
voice in the language the agent spoke (the `lang` of the answer, not the
page language). When no voice exists the questions stay on screen and
the conversation continues by voice input; when the microphone is
blocked or a browser will not restart it by itself, the panel shows one
tap per answer ("Toca em Falar para responder.") and the typed path
stays open.

Options considered: (a) client-side duration check only; (b) server
enforcement. Chosen (b): client hints differ by browser and cannot be
trusted for cost control. Options for the script: (a) inline in the
page; (b) a served file. Chosen (b): the policy forbids inline script
and a file can be tested and cached.

## T6. Transcription, extraction, the one question, confirmation

Decision: extend the existing `engine/model_client.py` pattern (model
`muse-spark-1.3`, standard library `urllib`, temperature 0, key from the
environment). Two clients behind small interfaces so tests stub both.

Transcription: `POST {META_API_BASE_URL or https://api.meta.ai/v1}/asr/transcribe`
with `Authorization: Bearer <key>` and a `multipart/form-data` body of
exactly two parts: `request` (`application/json`:
`{"model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV"}`) and
`audio` (`audio/wav`, mono 16-bit PCM at 16 kHz). The answer is
`{"sessionId", "transcript", "audioDurationMs", "turns": []}`.
`/audio/transcriptions` does not exist (404), `audioEncoding` is
required and `LINEAR16` with `sampleRateHertz` is refused, so neither is
sent.

Extraction: `POST /chat/completions` with model `muse-spark-1.3` and a
timeout of at least 30 s (about 450 reasoning tokens for a short
answer). The reply is parsed strictly as one JSON object with `intent`
(`update` or `question`), `language` (`pt` or `en`), `kind` and the
stated facts only; anything else is a `ModelError` and the typed path
stays open. Small transcription errors in names are tolerated by deal
matching, which compares the agent's own deals by words.

The conversation logic is `app/voice_flow.py`, plain app code: it
normalises the stated facts, decides which required fields are still
missing for the kind of update, matches the deal against the agent's own
deals (no match, or several, means one question naming the candidates)
and builds the one question and the one-line read-back. Required fields:
new deal (name, commission excluding IVA, own percentage, escritura
date, stage; CPCV date and agency only if spoken), CPCV signed (deal,
date), escritura date (deal, date), fell through (deal), commission
received (deal, amount, date), change stage (deal, stage), change
commission or percentage (deal, the new value), reopen (deal). Nothing
is saved before a spoken or tapped yes; the save goes through the normal
deal-writing path with an idempotency key from the conversation, so a
second confirm saves once. Conversations are kept in memory, tied to the
tenant that started them, and expire after two hours. A commission
received is stored in its own `receipts` table; `received` stays
derived and no stage is marked by hand.

After a read-back each answer is a correction. A field the agent names
(by words such as share, commission, date) without a usable value, or
with a negative one, is dropped and asked again (`app/voice_handlers.py`,
`voice_flow.fields_named`); an answer that changes nothing asks "What
should I correct?". `voice_flow.says_exact_date` makes what the agent
said beat extraction's estimated flag.

Options considered: (a) retry ambiguities silently; (b) one question to
the agent. Chosen (b): retries spend budget hiding the ambiguity the
agent must resolve.

## T7. The AI cost guard

Decision: a per-tenant daily counter table (`tenant`, `day`, `count`)
checked before any transcription or extraction call. At most 30
conversations per tenant per calendar day (Europe/Lisbon): a
conversation counts once, when it starts, and the turns of a running
conversation do not count again. Each conversation is also limited to 6
questions; the stop shows what was understood and saves nothing. The
31st conversation of a day is refused with a message in the page
language and no model call, for typed text and for audio alike. WAV
audio over 60 s, or with any other header than mono 16-bit PCM at
16 kHz, is refused before transcription with the page-language message.
Refusals leave stored data untouched and keep the typed and manual path
visible; they gate model spending, not record keeping.

Options considered: (a) per-session counters; (b) per-tenant daily
counters. Chosen (b): a session counter resets the budget on every
device, and the table survives restarts.

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

Estimated escritura date (Item 4): the deal stores an integer
`escritura_estimada` flag next to the date, and nothing is saved without
a date. A month given alone is stored as the 15th of that month with the
flag set; an exact date clears it, whether it arrives by voice or on the
deal form (the form has an \"Estimated date\" checkbox that the edit
form shows as stored). What the agent says beats the extraction's
`escritura_estimada` flag: a date said as exact or in full day, month
and year is stored exact (flag 0) even if extraction returns true. The flag changes how a date is shown
(\"(estimada)\" / \"(estimated)\" on cards, the table and the read-back,
\"meados de março\" / \"mid-March\"), never which month the deal counts
in: an estimated deal counts in its month's forecast like any other.

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
  data; sessions expire exactly 24 hours after creation with visits
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
3. A session expires exactly 24 hours after sign-in regardless of
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
- 24-hour session, secure HTTP-only cookie, per-device sign-out: T2,
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
- 24-hour non-sliding session: T2, criterion 3.
- Sign-in email in the page language at request time: T3.
- Accounts and isolation before voice and text: T11.
- Options and reasons per decision: recorded under each decision.
