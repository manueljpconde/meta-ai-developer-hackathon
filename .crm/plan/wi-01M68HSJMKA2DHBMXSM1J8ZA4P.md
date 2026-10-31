Discovery plan for the Agentimo multi-agent request. The business writer produces the functional decisions document under docs/decisions following the existing convention, iterates with the owner through request-scoped questions, and revises before seeking result approval. Owner approval of this discovery result is required before design starts.

```yaml crm-plan
phase: discovery
writer: business
assessors: [qa, architect]
budget_usd: 6
pool: preparation
route_overrides: {}
config_version: 12
scope:
  - docs/decisions/**
criteria:
  - 'Real app, no mock data. Remove the "Carregar exemplo / Load example" action, the example deals and the typed move scenario page. A new user starts empty, with a guided first deal.'
  - 'Portuguese (pt-PT) first, English available. Keep the PropWare styling. Single Hetzner box at `app.agentimo.propware.pt`.'
  - 'One agent per tenant. No agencies, no managers, no shared views.'
  - 'Sign-up and sign-in by email link only (no passwords). One flow: the first link creates the account.'
  - 'Links: random token, stored only as a hash, single use, valid 15 minutes, rate-limited per email and per IP.'
  - 'Session: 30 days, secure HTTP-only cookie, sign-out on the device.'
  - 'Email through the existing PropWare relay: Google Workspace SMTP relay `smtp-relay.gmail.com` with TLS, sender `hello@propware.pt`, standard library `smtplib`. Settings come from the app environment file; tests never send email.'
  - '"Delete my account" removes all of the agent''s data.'
  - 'Every stored row carries its tenant; every query is scoped by it. Tests prove one agent cannot read or change another agent''s deals, notes or settings, including by guessing ids.'
  - 'One box on the main page: record a voice note in the browser, or type.'
  - 'Supported updates: new deal; CPCV signed; escritura date set or moved; deal fell through; commission received.'
  - 'Meta transcription (`muse-voice-transcribe-1.0`) turns speech into text; a Muse model extracts the structured change. When something is missing or ambiguous it asks one question instead of guessing.'
  - 'Confirmation card before saving: the extracted fields (editable) and the forecast before and after. Nothing is saved without Confirm.'
  - 'Audio is deleted after transcription; the transcript and the confirmed change are kept.'
  - 'Every euro comes from the existing deterministic engine, never from the model.'
  - 'Python standard library only, as today. No external scripts or assets in pages.'
  - 'Tests first; no network calls in tests (stub the model, transcription and SMTP).'
proof:
  - python3 -m unittest discover -s engine/tests -t .
  - python3 -m unittest discover -s app/tests -t .
target_branch: main
```