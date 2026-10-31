Item 2c reopened from kept commit: sign-in, empty states and deal management in app only.

```yaml crm-plan
phase: build
writer: builder
assessors: [business, qa, code_review]
budget_usd: 12
route_overrides: {}
config_version: 15
scope:
  - 'app/**'
criteria:
  - 'While signed out, the only control in the header is a compact PT | EN language switch, with Portuguese (pt-PT) as the default. The app menu (Previsão/Forecast, Novo negócio/New deal, Mover pagamento/Move payment, Definições/Settings) appears only after a successful sign-in. A test asserts the menu is absent from every signed-out page and present once signed in.'
  - 'The same compact PT | EN switch replaces the full-width language form, with its dropdown and "Mudar/Change" button, on every page, signed in or out.'
  - 'The sign-in page shows the Agentimo name at the top, the line "Introduz o teu email e enviamos-te um link de acesso" / "Enter your email and we will send you a sign-in link", the email field and the "Enviar link / Send link" button, centred, in the existing PropWare styling.'
  - 'After a link is sent, a "Verifica o teu email / Check your email" page names the address and says the link is valid for 15 minutes. Errors show on the same page in the page language, never as a bare error page. That covers an invalid email, a rate limit, and an expired or missing form token, which today returns a bare 403.'
  - 'The "Carregar exemplo / Load example" action is removed entirely: its button and link, the example deals and the example route. A test proves no page offers it and the route is gone. The empty forecast shows one call to action, "Novo negócio / New deal".'
  - 'Each deal in the forecast list links to its edit page. The edit page has "Apagar negócio / Delete deal" with a confirmation step, and a deleted deal leaves the forecast immediately. Edit and delete are tenant-scoped: another agent deal id yields nothing and changes nothing, with tests.'
  - 'Deal and settings forms label every unit (€, %). Implausible input is either refused with a clear message in the page language or confirmed explicitly by the agent. That covers a share entered as "4" when 40 % is likely, an agency commission under €100, and negative or empty amounts.'
  - 'Every page has exactly one top-level heading (h1).'
  - 'Every data route requires a signed-in agent behind the default-deny session gate, and every row is tenant-scoped: every new route and table stays behind the gate and is scoped by tenant, with isolation tests.'
  - 'A smoke test starts app.server on a free port and drives it over HTTP with the standard library (urllib), not only through the in-process client.'
  - 'Full journeys, in Portuguese and English: request a link, open it, signed in, save settings, create a deal (agency commission €10 000, share 40 %) where the forecast shows the euros computed independently in the test, edit the deal, delete it, extended with the new behaviour of this item.'
  - 'QA runs the smoke and journey rules as a diagnostic at the reviewed commit and cites it in its verdict, with no go without it.'
  - 'Both suites are green: `python3 -m unittest discover -s engine/tests -t .` and `python3 -m unittest discover -s app/tests -t .`.'
  - 'The result description maps every criterion to the named test(s) that prove it; a criterion without a test is not done.'
proof:
  - 'python3 -m unittest discover -s engine/tests -t .'
  - 'python3 -m unittest discover -s app/tests -t .'
target_branch: main
```
