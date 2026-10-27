# Agentimo: minimum sufficient technical design for the hackathon

Status: proposal for a decision. Conditional where external evidence is
missing (section G). No implementation, deployment, or issue change is
proposed by this document itself.

Analyzed repository state: branch `crew-readiness`, commit
`5ebba6f896b8cd5c081f70e048daa4943c1c4c8d`. Supplied external context is
dated 27 October 2026 (hackathon page, import PR #1, original issue #1);
it was not re-retrieved, and the complete official rules were not
available.

## A. Evidence

Classification key: **Implemented** = code present and checkable in the
repository; **Simulated** = behaviour faked with prepared data;
**Specified** = design text only, no implementation; **Hypothesis** =
asserted need or value, not yet validated with users.

| Element | Class | Repository reference |
| --- | --- | --- |
| Product promise: see expected commission, money to protect, and money really available | Hypothesis to validate commercially | `docs/mvp-analysis.md` sections 1-3, 7: based on one association director's account; willingness to pay is explicitly unvalidated |
| Deterministic calculation engine: integer cents, no floating point for money, half-up rounding per component, frozen settlement outputs | Specified, not implemented | `docs/superpowers/specs/2026-10-03-product-core-design.md` sections 3, 5 |
| Negocios, payment parts, settlements, expenses, forecast, onboarding | Specified, not implemented | Same spec, sections 4, 6-8 |
| Foundation: Laravel + Inertia/Vue, PostgreSQL, Paddle billing, magic-link sign-in, two-layer per-agent isolation, lapse/erasure lifecycle, three interface languages | Specified, not implemented | `docs/superpowers/specs/2026-10-03-foundation-design.md` sections 3-4, 14 |
| Receipt assistant: copy sheet from a frozen settlement, manual issuance on the Portal das Financas, receipt recorded by typing or deterministic PDF extraction (QR code or text layer), no OCR/LLM extraction, no Portal automation, no AT credentials | Specified, not implemented; two implementation gates open (representative Portal PDF; upload-closure proof for the chosen storage) | `docs/superpowers/specs/2026-10-03-receipt-assistant-design.md` sections 2, 4.3-4.4 |
| Core journey UX (first negocio, forecast, payment confirmation) | Specified; approved only for the throwaway prototype, untested with agents | `docs/superpowers/specs/2026-10-04-ux-design.md` sections 3, 5-6 |
| Working prototype of the core journey and two self-guided demonstrations | Implemented as a disposable prototype; **simulated**: every figure is a prepared fixture literal, no calculation engine runs | `prototype/app.js`, `prototype/demo.js`, `prototype/fixtures.js`; UX spec section 5 ("It implements no calculation", "It is disposable") |
| Demonstration comments service (one file per comment, moderation) | Implemented for the prototype demonstration only; not a product feature | `prototype/publicacao/`, `prototype/testes/comentario-servico.test.mjs` |
| Original MVP excludes AI | Existing decision | `docs/mvp-analysis.md` section 6 ("IA, recomendacoes e saude financeira automatica: nao sao necessarias") |
| Hackathon judging, tracks, deadline (4 November 2026, 9:00 PM ET) | Supplied context only; complete rules, track selection, eligibility of pre-existing code, model access and credits all unverified | Brief section 2; no repository evidence |

Conclusions from the evidence:

1. Nothing in the planned production stack (Laravel, PostgreSQL, Paddle)
   exists as code. Reusing it for the hackathon means building the
   foundation first, which the evidence does not justify for a
   demonstration (section D).
2. The prototype proves the journey is understandable as screens and
   prepared figures; it proves nothing about calculation, persistence,
   or AI. Its code is documented as disposable, so this proposal reuses
   its fixtures, journey, and wording, not its code as a product base.
3. The only specified AI-free gap a model can fill without touching
   financial authority is turning the agent's unstructured deal or
   payment text into a structured draft for confirmation. That is a
   departure from the MVP's "no AI" decision and from no other boundary:
   it does not change the receipt assistant's exclusion of OCR/LLM
   extraction, because it never reads fiscal documents.

## B. Recommendation

**Decision requested:** approve one primary journey for the hackathon —
"describe a deal in your own words, see what is really yours" — and
approve the explicit departure from the original MVP's exclusion of AI,
limited to interpretation of the agent's own free text. No other
existing decision is changed.

The journey, end to end:

1. The agent pastes or types an unstructured description, for example a
   note or message: "Sold T2 in Alvalade through Agency X, agency
   commission 8,000 EUR plus IVA, my share 50%, expected November,
   confirmed."
2. One model call proposes the structured negocio fields (section C.3).
   Amounts are extracted, never calculated, by the model.
3. The agent reviews the draft beside the source text, corrects any
   field, and confirms. Nothing is a financial record before this
   confirmation.
4. Deterministic code runs the specified calculation rules and shows the
   four distinct values for the expected month: commission, expected
   bank inflow, money to protect, and really available — with the
   breakdown, exactly as specified in the product core spec section 5.5.
5. The agent records the payment when it arrives (actual amount and
   date, explicit confirmation; residual handled by the specified
   resolution choices, simplified to still-due / smaller / larger
   commission), and sees received versus expected and the updated
   available figure.

Concrete benefit: the agent's real difficulty is translating scattered
deal knowledge into the structured record that makes the forecast
possible; the MVP analysis already targets under 60 seconds for manual
entry and identifies manual-entry friction as the abandonment risk.
AI removes the transcription step, not the judgement: the agent still
confirms every field before any figure is computed.

What AI contributes, compared with the same journey without AI: steps
1-3 replace form-filling with review-and-correct. Without AI the demo
is the existing prototype with a real engine behind it — credible, but
indistinguishable from a form. With AI the demonstration shows the
product interpreting real-world messiness safely, with deterministic
money math the model never touches. That maps to the supplied judging
emphasis on creativity and technical ambition while "whether the
project works" rests on the deterministic core; for a production-
readiness reading, the same boundary (model proposes, code decides,
human confirms) is the defensible property. Track selection is not
established (section G), so no track-specific claim is made.

New hackathon contribution: the interpretation step, its validation
and confirmation design, and a working deterministic engine behind the
already-specified journey. Pre-existing code and specifications are
reused as evidence and fixtures, subject to the unverified rules on
pre-existing code (section G).

Simplest credible alternative, for comparison: ship the deterministic
journey with manual structured entry only (no model call). It is
cheaper and has no model-access dependency, and it is the fallback if
the experiment in section E fails. It is not recommended as the primary
because it demonstrates nothing the prepared prototype does not already
show, and it leaves the entry-friction risk unaddressed.

## C. Minimal technical design

### C.1 Diagram

```text
Agent browser
  |  free text / corrected draft / payment confirmation
  v
Single web application (one process, server-rendered pages)
  |-- Interpretation adapter ----> Meta model endpoint (one call)
  |     returns proposed fields only; no persistence, no money math
  |-- Deterministic engine (pure functions, integer cents)
  |-- Record store (single database, owner-scoped rows)
  v
Forecast view: commission | bank inflow | to protect | really available
```

No other services. No queue, no vector store, no orchestration, no
second agent: none is needed by any step of the journey.

### C.2 Components

- **Web application.** Serves the three screens of the journey (describe
  and confirm; forecast; record payment), following the UX spec's core
  journey wording and labels. Implementation language and framework are
  chosen at build time for the smallest deployable unit the team can
  run; this departs deliberately from the planned Laravel/PostgreSQL
  foundation, which is commercial scope, not demonstration scope
  (section D). The departure is safe because no foundation behaviour
  (accounts, billing, isolation at two layers, lapse, erasure) is
  claimed by the demo.
- **Deterministic engine.** A direct, reduced implementation of the
  product core spec section 5: integer cents, exact decimal rates,
  half-up rounding per component, IVA and retencao from the agent's
  own settings, reserves floored as specified, four labelled outputs.
  One negocio, one expected part, expenses entered as a single monthly
  total (expected or paid) — enough for the journey; split parts,
  recurring rules, replacement chains, and history are out (section D).
  Settings are entered once by the agent; the model never supplies
  rates, tax values, or missing facts.
- **Record store.** One database holding, per demonstration user: the
  confirmed negocio, its settings snapshot used for expected figures,
  and at most one settlement (received amount, date, frozen outputs).
  Records are created only by explicit confirmation. Synthetic data
  only for the public demonstration; if real pilot data is ever used,
  per-user isolation and access control become a precondition, not part
  of this design.

### C.3 The AI step, precisely

- **Input:** the agent's free text (length-capped) plus the field schema.
  No financial records, no documents, no PDFs.
- **Output:** a JSON object proposing only: negocio name, agency name,
  agency commission base (EUR, as stated), agent share percentage (as
  stated), expected month, stage (potencial / provavel / confirmado).
  Any field not stated in the text must be returned as null, never
  guessed.
- **Validation (deterministic, before display):** schema and type check;
  amounts parsed to integer cents by code, rejecting ambiguous formats
  rather than cleaning them; share within 0-100%; month a real future
  or current month; stage one of the three codes. A field failing
  validation is shown empty and marked for the agent to fill.
- **Ambiguity handling:** null or invalid fields are presented as
  questions on the confirmation screen, beside the source text. The
  model is not re-asked to guess.
- **Confirmation:** the agent edits and confirms; only then is a record
  created and the engine run. This is the boundary: the model proposes,
  deterministic code validates and calculates, the human decides.
- **Failure behaviour:** on timeout, error, or invalid output, the same
  screen falls back to manual structured entry pre-filled with any
  valid fields. The journey never blocks on the model.
- **Limits:** one call per submission, no automatic retries, a fixed
  output-token cap sized to the schema, a request timeout. Call and
  token counts are logged without the text content.

### C.4 Data flow and failure handling

Free text -> interpretation -> validated draft -> agent confirmation ->
engine -> forecast. Payment: agent-entered actuals -> engine frozen
settlement -> received/available view. Engine failure or invalid
settings (for example rates outside 0-100%) refuses confirmation with
the field error shown; nothing partial is saved. Model unavailability
degrades to manual entry (C.3). Persistence failure saves nothing and
says so; re-submission is safe because records are created only by the
single confirmation action carrying a client-generated idempotency key.

## D. Necessity table

| Component | Required capability | What fails without it | Simpler alternative | Decision |
| --- | --- | --- | --- | --- |
| Deterministic engine (reduced, C.2) | Correct, auditable money figures; the four distinct values | The product promise itself; every figure becomes a prepared fixture again | Model-computed figures — rejected: model is not the arithmetic authority | Keep |
| Interpretation adapter (one model call) | Turn free text into a confirmable draft | The AI contribution and the entry-friction reduction; journey degrades to a form | Manual structured entry — kept as the built-in fallback, not the primary | Keep, conditional on section E experiment |
| Confirmation screen (draft beside source text) | Explicit human approval before any financial record | AI suggestions would create records unreviewed; correctness criterion fails | Auto-save with undo — rejected: weaker guarantee, more states | Keep |
| Record store (one database) | Confirmed negocios and settlements survive between the forecast and payment steps | The journey cannot span "expected" to "received" | In-memory/session state — rejected: payment step may happen days later | Keep, minimal schema |
| Agent settings entry (IVA, retencao, reserve rates) | Figures reflect the agent's own situation; no tax advice given | Engine would need invented defaults — prohibited | Hard-coded example rates — rejected for the live journey; used only in fixtures | Keep |
| Foundation: accounts, Paddle billing, two-layer isolation, lapse/erasure, admin, three languages | Commercial operation | Nothing in the demonstration journey | Demonstration on synthetic data with a single shared demo user | Remove from hackathon scope; remain planned product scope |
| Receipt assistant, PDF extraction, file store | Record issued receipts without retyping | No hackathon criterion: it is a separate journey from the primary one, with two open implementation gates | Copy sheet values from the forecast by hand during the demo narrative | Defer entirely to post-pilot decision; boundaries preserved unchanged |
| Expenses as recurring rules, split payment parts, replacement chains, 12-month forecast/history | Full product-core fidelity | Nothing in the primary journey, which uses one negocio, one part, one monthly expense total | Monthly expense total (chosen) | Defer |
| Multiple agents, RAG, vector database, queues, microservices, orchestration framework | None demonstrated | Nothing | Single process and one model call (chosen) | Remove |
| Chatbot interface | None beyond the interpretation step | Nothing; free-text input is a field, not a conversation | Structured form with one free-text field (chosen) | Remove |
| Prototype code reuse | A running start | Nothing if rebuilt small; prototype is documented disposable and computes nothing | Reuse fixtures, journey, and wording only (chosen) | Do not build on prototype code |

## E. Feasibility

**Resources.** No new paid services. Needs: one deploy target for a
single web process plus one small database (an existing or free tier
the team already controls — unverified, section G), and runtime access
to a Meta model endpoint for the product itself. The design crew's
model gateway is not assumed available to the product.

**Effort (estimates, one developer):** engine with tests, 0.5-1 day;
three screens with confirmation flow, 1-2 days; interpretation adapter
with validation and fallback, 0.5 day; deployment and demonstration
script, 0.5 day. Total roughly 3-4 days inside the 26 October -
4 November window, leaving review time. These are planning estimates,
not measurements.

**Model cost.** Exactly one call per deal submission; no call for the
forecast, payment, or any other step. Token assumption per call: input
is the agent's short text plus schema (order of a few hundred tokens);
output is the small field JSON (order of one hundred tokens, capped).
Cost per journey = 1 x (input tokens x input price + output tokens x
output price); cost per 100 journeys = 100 x that. Prices, quotas, and
even endpoint access are unknown (not supplied), so no numeric cost is
claimed — the formula and the token counts above are what must be
priced once access is confirmed. After any temporary credits expire,
the same formula applies at the then-current price; if no paid access
is acceptable, the fallback is manual entry and the model call is
disabled, with no other change.

**Model selection.** The least expensive Meta model that passes the
experiment below. Capability is not asserted in advance.

**Smallest experiment that could invalidate the proposal:** before
building the journey, run 15-20 synthetic free-text deal descriptions
(including ambiguous ones: missing share, missing month, amounts with
and without IVA mentioned) through the candidate endpoint. Pass bar:
every amount and percentage extracted exactly as stated or returned
null, no invented values, valid schema output in all cases. If the
cheapest available model invents figures or cannot follow the
null rule, the AI step is not safe as designed: fall back to the
manual-entry alternative in section B rather than weakening the
confirmation boundary.

**Delivery sequence:** (1) run the experiment and record the result;
(2) engine plus tests against the product core spec's worked examples;
(3) screens and confirmation flow with manual entry; (4) interpretation
adapter behind the same confirmation screen; (5) end-to-end checks in
section F, then freeze for submission.
