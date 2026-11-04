# Agentimo

![An independent agent in Lisbon updates their forecast by voice](docs/assets/agentimo-banner.jpg)
<sub>Banner generated with Meta's Muse Image.</sub>

**See how much of your commission is really yours, and keep it up to date by just talking.**

Agentimo is a cash-flow forecast for independent real-estate agents in Portugal, built by PropWare (CrmWare) for the [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/). Startups track, theme "Build for Your World".

- **Live:** https://app.agentimo.propware.pt
- **Demo video (3 min):** https://www.youtube.com/watch?v=0M3KLqLW5Tk

## The problem

In Portugal, an independent agent is paid a share of the agency's commission. That money arrives months after the deal, with IVA (VAT) collected on top and income tax withheld. Before any of it is really theirs, the agent still has to set aside IRS and Social Security and pay their own fuel, lunches and phone. The director of a Portuguese real-estate association told us agents routinely treat the commission as profit and find out at year end that they earned far less. Most keep track in a spreadsheet, if at all.

## What Agentimo does

For every month, it answers three questions: what will reach my account, what must I protect, and what is really mine?

- **Forecast dashboard.** It shows the last three closed months and the next three expected ones. The expected months are split into confirmed, likely and potential deals, and a chart of what is really yours per month marks any month that goes negative.
- **Expenses with honest rules.**
  - A past month subtracts the expenses actually recorded.
  - A future month subtracts the agent's own estimate plus any planned expenses, so the agent never counts on money they will spend.
  - The current month subtracts the larger of what is recorded so far and the estimate.
- **One Speak button.** "New deal, a T4 in Infantado, December, 10,000 euros, 3%, potential." Agentimo asks only for what is missing, reads the deal back in one line and saves it when the agent says "yes". Changes ("the Alvalade deal moved to March") and expenses ("120 euros of lunch with client Alberto for the Infantado deal") work the same way.
- **Per-deal view.** Each deal shows what it leaves and its linked expenses. "Comissão" always means the agency's commission; the agent's part is "A tua parte" (your share).

## How it works: Meta's models interpret, deterministic code decides

```
voice (browser, 16 kHz WAV)
  → Muse Voice Transcribe 1.0   page language + domain keywords
  → Muse Spark 1.3              one JSON object: intent, kind, stated facts only
  → application code            missing fields, deal matching, one-line read-back
  → engine.calc                 every euro, in integer cents
  → agent says "sim"/"yes"      only then is anything saved
```

- **The model never touches money.** Amounts are computed by `engine/calc.py` from exact decimal rates, in integer cents, rounding half-up per component. The model only proposes the facts the agent stated.
- **Measured before we built on it.** `experiments/extraction` ran 60 agent notes in Portuguese and English through 5 prompt variants. Every response was valid JSON. Muse Spark never invented a field or returned anything unsafe, and 95% of fields were correct on both the tuning set and the held-out set.
- **Tuned for latency.** Muse always reasons. With `reasoning_effort: "minimal"`, a test utterance gave the same JSON in 4.2 s with 326 reasoning tokens, against 9.3 s and 1,209 tokens at the default. A production turn went from 12–30 s to about 3–10 s.
- **Built to hold up in production.**
  - Sign-in by email link: opening the link changes nothing; only the Sign in POST uses it.
  - Every query is scoped to the agent's own tenant.
  - Every POST is CSRF-checked, and the page runs under `default-src 'self'`.
  - Each agent gets 30 voice conversations a day, and the limit is refused before any model call.
  - Voice is tested on a real iPhone.

## Built with Meta, end to end

- **In the product:** Muse Voice Transcribe 1.0 and Muse Spark 1.3, through the Meta Model API.
- **In the specification:** Muse Code.
- **In this README:** the banner was made with Muse Image.
- **In the build:** Agentimo was planned, written, tested and reviewed by CrmWare's autonomous software crew. Coordinator, architect, builder, QA, business reviewer, code reviewer and integrator run as agents, and the owner approves each plan and each result. The crew runs on Meta models:
  - Muse Spark 1.3, through the Meta Model API, in every role;
  - Muse Spark Open, Meta's open-weights model, on Baseten, for the builder, QA, business and code-review roles;
  - Muse Wonder 1.0, for the architect.

## Run it

Python 3.12, standard library only.

```bash
python3 -m unittest discover -s engine/tests -t .   # calculation engine
python3 -m unittest discover -s app/tests -t .      # app, voice and HTTP tests (models are stubbed)

META_API_KEY=... APP_DB_PATH=./agentimo.db python3 -m app.server   # http://127.0.0.1:8000
```

Sign-in links are emailed through an SMTP relay configured with `PROPWARE_RELAY_*`. Set `APP_BASE_URL` to the public address. `deploy/` holds the systemd unit, the Caddy configuration and `deploy/smoke.py`, a smoke test for a live deployment.

## Repository

| Path | What it is |
|---|---|
| `engine/` | Calculation engine: per-part and per-month figures, the monthly expense rule |
| `app/` | Web app (`web.py`), storage (`store.py`), voice (`voice*.py`, `static/voice.js`), PT and EN strings (`i18n.py`) |
| `app/tests/`, `engine/tests/` | Test suites |
| `docs/decisions/` | Owner decisions, including `expense-rules.md` and the voice criteria map |
| `docs/mvp-analysis.md` | Product analysis and evidence (in Portuguese) |
| `experiments/extraction/` | The extraction quality experiment and its results |
| `prototype/` | The pre-hackathon click-through prototype we used to collect feedback from agents (live at https://demo.agentimo.propware.pt) |

## History

Agentimo started from a real conversation, not from code. The director of a Portuguese real-estate association described how independent agents treat their commission as profit and find out at year end that they earned far less. That became the product analysis and the specifications in `docs/`.

Before writing any product code, we tested the idea with target users. The commits dated before 2026-10-26 hold a disposable click-through prototype that walks agents through the proposed journeys and lets them leave feedback. It is still online at https://demo.agentimo.propware.pt. That feedback is what led us to go ahead and build the MVP, Agentimo.

Those pre-hackathon commits were imported from the original private repository with their history intact. They contain the product analysis, the specifications and the prototype only. All product code (`app/`, `engine/`) was written during the hackathon.

## License

GNU Affero General Public License v3.0 (AGPL-3.0). See `LICENSE`.
