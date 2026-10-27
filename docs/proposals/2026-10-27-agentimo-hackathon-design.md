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
