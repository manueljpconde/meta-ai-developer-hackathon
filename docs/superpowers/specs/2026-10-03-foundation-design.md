# Foundation — design

Date: 2026-10-03

Status: design approved in conversation; awaiting written-spec review

Tracking: [issue #2](https://github.com/CrmWare/propware-agentimo/issues/2)

## 1. Purpose

The foundation is everything the product features stand on: the stack, accounts and sign-in, paid access through Paddle, per-agent data isolation, the lapse lifecycle, the internal admin panel, and the deployment baseline.

It delivers no product feature. It is complete when a new agent can sign up, pay, reach an empty authenticated app, lapse through every access phase, renew, and be exported or erased by an admin, with isolation proven at both layers.

The MVP is split into three specs:

1. Foundation (this document).
2. Product core: the four MVP features and onboarding. Not yet written.
3. Receipt assistant: `2026-10-03-receipt-assistant-design.md`.

## 2. Scope

In scope:

- Accounts and magic-link sign-in.
- Paddle subscriptions, checkout and webhooks.
- Access phases and their enforcement.
- Per-agent isolation in the application and in PostgreSQL.
- Admin panel with audit log, export and erasure.
- Self-service data export for active agents.
- Deployment baseline and `docs/deployment/PRODUCTION_GAPS.md`.

Out of scope:

- Negócios, financial profile, expenses and forecast (product core spec).
- Receipt assistant.
- Teams, accountants or any shared access.
- Password sign-in for agents.
- In-app refunds.
- Free tier.
- Trials without a payment method.

## 3. Architecture

- One Laravel application.
- Agent-facing app: Inertia with Vue, mobile-first.
- Admin panel: Filament, at a separate path, with its own guard.
- PostgreSQL.
- A queue worker and the scheduler.
- Cashier Paddle for billing.
- Interface and emails in European Portuguese.
- Money is stored as integer cents everywhere.

### 3.1 Two kinds of table

**Agent data.** Every table holding an agent's business data (negócios, expenses, financial profile, receipts, and anything added later). Every row carries its owner. Both isolation layers apply.

**Platform data.** Users, magic-link tokens, sessions, Cashier's customer, subscription and transaction tables, admins, and the audit log. These are not under row-level security, because sign-in and Paddle webhooks must read them before any agent is in context. Application code reaches them only by the authenticated user's key.

## 4. Isolation

The agent is the tenant. There is no shared data between agents.

### 4.1 Layer 1: application scope

- One shared trait on every agent-data model:
  - filters every query to the signed-in agent;
  - sets the owner on creation;
  - throws when no agent is in context, instead of returning unscoped results.
- Policies check ownership on each action.
- Another agent's identifier returns "not found".
- An architecture test fails the build if a model on an agent-data table lacks the trait.

### 4.2 Layer 2: row-level security

Three database roles:

| Role | Used by | Row-level security |
| --- | --- | --- |
| Migration | Migrations only. Owns the tables. | Not used at runtime |
| Application | Web requests, agent jobs, Paddle webhooks | Enforced, no bypass right |
| System | Admin panel, cross-agent system jobs | Bypasses |

- Row-level security is enabled and forced on every agent-data table.
- The policy compares the row's owner with a per-connection setting, for reads and for writes.
- Middleware sets the setting after authentication. A job middleware sets it for queued agent jobs.
- The setting is cleared at the start and at the end of every request and job, so a reused connection never carries the previous agent.
- With the setting absent, the policy matches no rows and rejects writes.
- No transaction-pooling proxy sits in front of PostgreSQL. If one is ever added, the setting moves inside a per-request transaction.
- A test queries the database catalogue and fails if any table with an owner column lacks a forced policy.

Paddle webhooks touch only platform tables, so they run on the application role with no agent in context.

The system role is used through a separate database connection that only the admin panel and named system jobs reference.

## 5. Accounts and sign-in

### 5.1 Agents

- Sign-up and sign-in use the same flow: the agent enters an email and receives a magic link.
- A new agent continues directly to checkout.
- Tokens are random, stored only as a hash, single-use, and valid for 15 minutes.
- Opening the link shows a "Continuar" button. Only pressing it consumes the token, so mail scanners that pre-open links cannot burn it.
- The response to a link request is identical whether or not the email has an account.
- Link requests are rate-limited per email and per IP.
- The session is regenerated on sign-in.
- If an agent loses access to their mailbox, an admin changes the email in the admin panel after verifying the agent out of band.

### 5.2 Admins

- Admins live in their own table and use their own guard.
- Sign-in is by password with mandatory two-factor authentication.
- An agent session cannot reach the admin panel, and an admin session cannot reach the agent app.

## 6. Billing

- Paddle is the merchant of record. It invoices agents and handles VAT on the subscription.
- Plans: monthly at 15 EUR and annual at 150 EUR, defined as Paddle prices. Displayed prices include VAT.
- Subscribe first: an agent with no subscription can reach only the checkout.
- The annual plan is charged at subscription.
- Checkout is Paddle's overlay checkout, tied to the agent through Cashier.

### 6.1 Free first month

- The monthly plan starts with a free first month. A payment method is required at checkout, nothing is charged then, and Paddle charges the first 15 EUR automatically 30 days later unless the agent cancels.
- The free month is a trial period on a Paddle price. Two monthly prices exist at 15 EUR: one with the trial, one without.
- One free month per agent. The app offers the trial price only to an agent who has never had a subscription; a returning agent gets the price without trial and is charged immediately.
- The annual plan has no free period.
- During the free month the agent is in the Active phase.
- This replaces the "no free period" rule in `docs/mvp-analysis.md` §7. The pilot's payment signal becomes conversion at day 30, and that section must be amended.

### 6.2 Single source of truth

- Access is derived only from Cashier's subscription rows.
- Only webhooks change those rows.
- Returning from checkout grants nothing. The page shows "a confirmar pagamento" and polls until the webhook has been processed.

### 6.3 Webhooks

- The signature is verified. Unsigned or wrongly signed requests are rejected.
- Each event is processed once, keyed by its event ID.
- Each event is processed inside a database transaction.
- Out-of-order delivery is tolerated: an older event never overwrites newer state.

### 6.4 Self-service

- The agent can switch plan, update the payment method and cancel.
- Cancelling takes effect at the end of the paid period, or at the end of the free month.
- Refunds are done by an admin in Paddle.

## 7. Access phases

The phase is computed on each request from the subscription rows and the lapse timestamp. Enforcement never depends on a scheduled job having run.

Lapse is the moment the paid period or the free month ends without a successful charge: either a cancelled subscription reaching the end of its period, or Paddle ending the subscription after its payment retries fail.

| Phase | When | Allowed |
| --- | --- | --- |
| No subscription | Signed up, never subscribed | Checkout only |
| Active | Free first month and paid period, including Paddle's payment retries | Everything |
| Read-only | Days 0 to 30 after lapse | View data; renew |
| Locked | Days 30 to 60 after lapse | Renew; see support contact |
| Marked for deletion | From day 60 after lapse | Renew; see support contact |

Rules:

- A single middleware on every agent route enforces the phase.
- In read-only, every write, export and file download is rejected server-side. Hiding controls in the interface is not the enforcement.
- In locked and marked, no agent data is served.
- A successful payment in any phase before erasure restores full access and clears the lapse timestamp and the deletion mark.
- Erasure of a marked account is performed only by an admin, manually. There is no automatic erasure.

### 7.1 Scheduled job

A daily job, on the system role:

- stamps the deletion mark on accounts reaching day 60;
- sends the lifecycle emails.

Lifecycle emails: on lapse, seven days before locking, on locking, seven days before marking, and on marking. Each email is sent once per lapse.

## 8. Admin panel

Allowed:

- List agents with phase, subscription status, lapse date and deletion-mark date.
- Change an agent's email.
- Export an agent's data.
- Erase an account.

Not allowed:

- Browsing or editing an agent's business data. The panel reaches agent data only to export or erase it.

Audit log:

- Every admin action is recorded: which admin, what action, when, and which agent.
- The log is append-only. No update or delete path exists in the application.
- An erasure entry keeps the event but no personal data of the erased agent.

## 9. Data protection

### 9.1 Export

- An active agent can export their own data in the app.
- In read-only, locked and marked phases, the in-app export is unavailable. An admin produces the export from the admin panel on request, within the legal one-month limit.
- The export contains every agent-data table and any stored files. Each later spec adds its own data to the export.

### 9.2 Erasure

- Performed by an admin, on the agent's request or for a marked account.
- Order: cancel any live Paddle subscription, then remove agent data, stored files, the user, sessions and tokens.
- Paddle keeps its own billing records as merchant of record.
- Erasure requires an explicit confirmation and is irreversible.

### 9.3 Retention

- Agent data is kept while the account exists.
- After the deletion mark, retention is at the operator's discretion until an admin erases the account. The privacy policy states this.
- Backups are daily, encrypted, and kept for 30 days. Erased data leaves backups as they rotate. Restore is tested.

### 9.4 Legal pages

- Privacy policy and terms, stating the lapse lifecycle and the retention rule.
- Agentimo sets only essential cookies. Whether Paddle's checkout script sets cookies that need consent is verified during the implementation plan.

## 10. Deployment baseline

- Containers: app, queue worker, scheduler, PostgreSQL.
- Hosted in an EU region. The spec is provider-neutral.
- Email goes through Laravel's mail configuration; the delivery provider is a setting.
- HTTPS only.
- Security headers, with a content security policy that allows Paddle's script and nothing broader.
- Secrets exist only in the environment, never in the repository.
- Logs contain no email addresses, tokens or payment data.
- `docs/deployment/PRODUCTION_GAPS.md` is created with the foundation, tracked in the repository, and lists what is not production-ready.

## 11. Testing

Tests are written before implementation.

Isolation, application layer:

- Agent B cannot read, change or delete agent A's rows.
- A query with no agent in context throws.
- The architecture test catches an agent-data model without the trait.

Isolation, database layer:

- Raw SQL as the application role returns nothing with no agent set.
- Raw SQL as the application role returns nothing of another agent's.
- Cross-agent inserts and updates are rejected.
- The catalogue test catches an owner-column table without a forced policy.
- The setting is cleared between consecutive requests and jobs on a reused connection.

Sign-in:

- A token works once, and not after 15 minutes.
- Opening the link without pressing the button does not consume the token.
- Rate limits hold per email and per IP.
- Responses are identical for known and unknown emails.

Billing:

- Bad signatures are rejected.
- A replayed event changes nothing.
- An older event arriving late does not overwrite newer state.
- The checkout return grants no access before the webhook.
- A new agent on the monthly plan gets the trial price and full access with no charge.
- An agent who has had any subscription gets the price without trial.
- A free month that ends cancelled, or with a failed first charge, lapses into read-only.

Phases:

- Boundaries at days 29, 30, 59 and 60, using time travel.
- A test walks every agent route and proves it sits behind the phase middleware.
- In read-only, every write, export and download route is rejected.
- Renewal from each lapsed phase restores access and clears the marks.
- Each lifecycle email is sent once.

Admin:

- An agent session cannot reach the panel; an admin session cannot reach the agent app.
- Two-factor is required.
- Every action writes an audit entry; the log cannot be changed.
- Erasure leaves no rows or files of the agent behind.

End to end:

- One manual pass against Paddle's sandbox: sign up, start the free month, convert to paid, cancel, lapse, renew without a second free month.

## 12. Confirmed assumptions

- Displayed prices include VAT.
- Hosting is in an EU region.
- Backups are daily, encrypted and kept for 30 days.
