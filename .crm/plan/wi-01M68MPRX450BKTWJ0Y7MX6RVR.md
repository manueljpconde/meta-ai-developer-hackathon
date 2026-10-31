Design work item for the Agentimo accounts and voice updates request: produce the technical decisions document in docs/decisions/ following the #18 convention, building on the published discovery functional decisions and the owner's binding design amendments. Owner plan approval gates writing; owner result approval gates the build phase.

```yaml crm-plan
phase: design
writer: architect
assessors: [business, code_review]
budget_usd: 8
pool: preparation
route_overrides: {}
config_version: 12
scope:
  - 'docs/decisions/**'
criteria:
  - 'Real app, no mock data. Remove the "Carregar exemplo / Load example" action, the example deals and the typed move scenario page. A new user starts empty, with a guided first deal.'
  - 'Portuguese (pt-PT) first, English available. Keep the PropWare styling. Single Hetzner box at `app.agentimo.propware.pt`.'
  - 'One agent per tenant. No agencies, no managers, no shared views.'
  - 'Sign-up and sign-in by email link only (no passwords). One flow: the first link creates the account.'
  - 'Links: random token, stored only as a hash, single use, valid 15 minutes, rate-limited per email and per IP.'
  - 'Session: 30 days, secure HTTP-only cookie, sign-out on the device.'
  - 'Email through the existing PropWare relay: Google Workspace SMTP relay `smtp-relay.gmail.com` with TLS, sender `hello@propware.pt`, standard library `smtplib`. Settings come from the app''s environment file; tests never send email.'
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
  - 'AI cost guard: at most 30 updates per tenant per day, voice notes up to 60 s, and a clear message in the page language when the cap is reached.'
  - 'Existing live data (Deal Name 1 and the demo settings) is dropped when accounts go live; the first real account starts empty.'
  - 'The session lasts 30 days from sign-in, not sliding.'
  - 'The sign-in email uses the page language at the time of the request.'
  - 'Accounts and isolation are built before voice and text updates.'
proof:
  - 'python3 -m unittest discover -s engine/tests -t .'
  - 'python3 -m unittest discover -s app/tests -t .'
target_branch: main
```
