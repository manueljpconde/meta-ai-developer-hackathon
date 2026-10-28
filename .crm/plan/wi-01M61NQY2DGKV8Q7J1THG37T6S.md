Build the Agentimo first screens over engine.calc: settings once, Flow A manual negocio entry with Rever and Confirmar, Flow B Previsao forecast, in pt-PT and en-GB, changing only app/.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 20
pool: null
route_overrides: {}
config_version: 8
scope:
  - app/**
criteria:
  - |
    2. WHAT TO BUILD
    - Package `app/` at the repository root: a WSGI application (`app/web.py`, a callable `application(environ, start_response)`), a store (`app/store.py`, `sqlite3`), a runner (`app/server.py`, `wsgiref.simple_server`, address and database path from environment variables), one stylesheet under `app/static/`, and tests under `app/tests/`.
    - **One demonstration user**, no accounts. Every figure comes from `engine.calc`; the application performs no money arithmetic of its own.
    - **Two languages, `pt-PT` and `en-GB`, with a visible switch on every screen.** Follow `docs/superpowers/specs/2026-10-03-foundation-design.md` sections 14.1–14.4 (French is out of scope):
      - Wording comes from the UX glossary (UX 2.2), with one term per concept. In English, the fiscal terms stay in Portuguese (IVA, retenção na fonte, Segurança Social; foundation 14.4).
      - The first visit takes the language from `Accept-Language` by language family (any `en-*` gives `en-GB`, any `pt-*` gives `pt-PT`, anything else gives `pt-PT`). An explicit selection always wins after that and is kept in a cookie.
      - Display follows foundation 14.3: `5 000,50 €` and `novembro de 2026` in `pt-PT`; `€5,000.50` and `November 2026` in `en-GB`.
      - A language change never changes a stored value or a result (foundation 14.2). Stages are stored as language-neutral codes (`potencial`, `provavel`, `confirmado`), and text the agent typed is never translated.
      - Every translated string lives in one place per language (for example `app/i18n.py`). A missing translation is a test failure, never a silent fallback to Portuguese.
    - **Settings screen** (`Definições`): the agent's share (%), IVA (%), retenção na fonte (%), IRS reserve (%), Segurança Social reserve (%), and recurring monthly expenses (€). Entered once, editable. Rates are stored as exact decimal strings, amounts as integer cents. No setting has a default value: the UX example values are fixtures for tests only, never defaults.
    - **Flow A, record a negócio** (UX 3.1, wireframe W1): name, agency commission without IVA (€), the agent's percentage (pre-filled from settings), expected month, stage (Potencial / Provável / Confirmado), agency name (optional). The browser performs no arithmetic, so the flow has two steps:
      1. **Rever:** the form is submitted to the server, which validates it and shows the computed figures (A tua parte, and that month's four amounts) without saving anything.
      2. **Confirmar:** saves once. The server recalculates at confirmation. If the figures differ from those shown, nothing is saved, and the page shows the new figures with "Os valores foram atualizados. Revê antes de confirmar."
    - **Idempotent confirmation:** the review page carries a server-generated idempotency key. Confirming twice with the same key creates exactly one negócio.
    - **Validation:** messages appear beside the field, in the UX spec's words ("Indica a comissão da agência.") and their English equivalent. Invalid input refuses confirmation and saves nothing.
    - **Numeric input (amounts and percentages), following foundation 14.3:**
      - Each form declares its locale, and the server parses by that locale; it never guesses the separator.
      - A value is digits plus, optionally, the locale's decimal separator, with at most two decimals for amounts: `10000,00` or `10000` in `pt-PT`, `10000.00` or `10000` in `en-GB`.
      - Leading and trailing whitespace is trimmed. Internal spaces, thousands separators, symbols and the other locale's separator are refused, never cleaned. The message gives an example in the agent's locale ("Introduz o valor sem separadores de milhares: 5000,50." / "Enter the amount without thousands separators: 5000.50.").
      - The text the agent typed is kept in the field.
    - **Flow B, the forecast** (`Previsão`, UX 3.2, the home screen): for each month that has negócios, the four amounts with their own labels (Comissão, Entrará na conta, Dinheiro a proteger with its breakdown, É realmente teu), using that month's expenses, plus the list of that month's negócios. With no negócios, it shows the empty state and the "Novo negócio" entry point.
    - **Security:** every value written into HTML is escaped with `html.escape`. Every form POST carries a CSRF token tied to a session cookie (`HttpOnly`, `SameSite=Strict`). Responses send `Content-Security-Policy: default-src 'self'` and `X-Content-Type-Options: nosniff`. SQL uses parameters only. A refused or failed request saves nothing.
    - **Status is never colour alone;** every input has a visible label, and stage is a radio group labelled "Fase" (UX 3.1 accessibility).
  - |
    3. REQUIRED TESTS
    These are fixtures for tests only, from UX section 2.3: share 50 %, IVA 23 %, retenção 25 %, IRS 30 %, Segurança Social 10 %, expenses 350,00 €. Negócio "T2 Campo de Ourique", commission 10 000,00 €, November 2026, Confirmado.
    | Check | Expected |
    |---|---|
    | Review page for the example | A tua parte 5 000,00 €; Entrará na conta 4 900,00 €; Dinheiro a proteger 1 900,00 € (IVA 1 150,00; IRS 250,00; Segurança Social 500,00); É realmente teu 2 650,00 € |
    | Review does not save | the negócio count is unchanged after Rever |
    | Confirm, then the forecast for November 2026 | the same four values, and "T2 Campo de Ourique" listed |
    | Confirm twice with the same idempotency key | exactly one negócio |
    | Settings changed between Rever and Confirmar | nothing saved; the new figures are shown with "Os valores foram atualizados. Revê antes de confirmar." |
    | Missing commission | "Indica a comissão da agência." beside the field; nothing saved |
    | Percentage 150 | refused beside the field; nothing saved |
    | `pt-PT`: commission `10000,00`, `10000` and ` 10000,00 ` | accepted as 1000000 cents |
    | `pt-PT`: commission `10 000,00`, `10.000,00`, `10000.00`, `10000,005` and `10000 €` | refused beside the field with the `pt-PT` example message; the typed text is kept; nothing saved |
    | `en-GB`: commission `10000.00` | accepted as 1000000 cents |
    | `en-GB`: commission `10000,00` and `10,000.00` | refused with the `en-GB` example message; nothing saved |
    | Review page for the example in `en-GB` | Your share €5,000.00; Will reach your account €4,900.00; Money to set aside €1,900.00 (IVA €1,150.00; IRS €250.00; Segurança Social €500.00); Really yours €2,650.00; month "November 2026" |
    | Switch language after confirming | the stored negócio, its stage code and the forecast amounts are identical; only their display changes |
    | First visit with `Accept-Language: en-US` | `en-GB`; after an explicit switch to `pt-PT`, a later request with `Accept-Language: en-US` stays `pt-PT` |
    | Every string key used by the screens | present in both `pt-PT` and `en-GB` |
    | A negocio name containing script markup | rendered escaped on every page |
    | POST without a valid CSRF token | refused (403); nothing saved |
    | Forecast with no negócios | the empty state, with "Novo negócio" |
    Write these tests first, and commit and push them before the application, so the first commit fails.
  - |
    5. ASSESSMENT
    - QA: every check in section 3 is present and passes at the head, and the engine's tests still pass. Also try inputs beyond the listed tests (an empty name, a commission of 0, a month in the past, a very long name, a stage value outside the three, repeated submissions of the review form), and report what each one does.
    - Code review: standard library only. No money arithmetic outside `engine.calc`. All HTML output escaped, CSRF on every POST, parameterised SQL, the security headers present. No change under `engine/` or `prototype/`.
    - Business: the screens use the UX glossary's wording and labels for Flows A and B in both languages, and the fiscal terms stay in Portuguese in English. The four amounts are distinct and correctly labelled. No setting has a default value. Nothing is saved before Confirmar. A language switch changes no stored value.
proof:
  - "python3 -m unittest discover -s engine/tests -t . -v"
  - "python3 -m unittest discover -s app/tests -t . -v"
target_branch: main
```
