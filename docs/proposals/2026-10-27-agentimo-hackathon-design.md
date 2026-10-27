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
