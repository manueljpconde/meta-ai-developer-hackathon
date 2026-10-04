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
| System | Admin panel, named system jobs | Bypasses |

- Row-level security is enabled and forced on every agent-data table.
- The policy compares the row's owner with a per-connection setting, for reads and for writes.
- Middleware sets the setting after authentication. A job middleware sets it for queued agent jobs.
- The setting is cleared at the start and at the end of every request and job, so a reused connection never carries the previous agent.
- With the setting absent, the policy matches no rows and rejects writes.
- No transaction-pooling proxy sits in front of PostgreSQL. If one is ever added, the setting moves inside a per-request transaction.
- A test queries the database catalogue and fails if any table with an owner column lacks a forced policy.

Paddle webhooks touch only platform tables, so they run on the application role with no agent in context.

The system role is used through a separate database connection that only the admin panel and the named system jobs reference. The named system jobs are the lapse lifecycle job, erasure, erasure reconciliation, and receipt file cleanup (defined in the receipt assistant spec).

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
- Changing the email revokes, in the same database transaction, every session of that agent and every pending magic-link token. A session or link issued before the change never works after it.
- A notice of the change is sent to the previous address.

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
- One free month per agent. Eligibility is a server-side guarantee, not a presentation rule: an agent is eligible only while they have never had a subscription. A returning agent gets the price without trial and is charged immediately.
- The annual plan has no free period.
- During the free month the agent is in the Active phase.
- This replaces the "no free period" rule in `docs/mvp-analysis.md` §7. The pilot's payment signal becomes conversion at day 30, and that section must be amended.

### 6.2 Checkout authorisation and duplicates

Cashier's checkout passes the price to Paddle's script in the browser, so the price a checkout was opened with cannot be trusted.

- The server decides the authorised price for the agent and records a pending checkout: agent, authorised price, expiry. The pending checkout's identifier travels to Paddle as custom data.
- Every mirrored subscription has an admission state: pending, admitted or rejected. Only an admitted subscription grants access.
- Admission runs on the first Paddle data seen for a subscription, whichever event or API response carries it, and before any state from it can grant access. It does not depend on the subscription-created event arriving, or arriving first.
- Admission verifies that the pending checkout named in the custom data exists, belongs to this agent, authorises this price, and has not been consumed.
- A pending checkout is consumed once. Admission binds it to the accepted subscription under a unique constraint, so it can never admit a second subscription.
- Expiry is judged against the time the checkout completed at Paddle, taken from Paddle's data, never against the time the webhook was delivered. A checkout completed in time is admitted however late its webhook arrives.
- A rejected subscription grants no access and is flagged in the admin panel for refund. Its cancellation at Paddle is requested immediately, tracked on its mirror row, and retried until Paddle confirms the cancelled state.
- Consuming the free month is recorded on the agent in the same transaction that admits the first subscription.
- That the pending checkout's identifier is present on the subscription data of every relevant event is validated in Paddle's sandbox during the implementation plan.
- One admitted live subscription per agent, enforced by a unique constraint over admitted live rows only. Pending and rejected subscriptions are mirrored alongside it and grant no access, so the mirror can faithfully record a second subscription that exists at Paddle while its cancellation is pending or failing.
- The server refuses to open a checkout while the agent has an admitted live subscription or an unexpired pending checkout.
- If two subscriptions are nevertheless created, the first admitted one stands. The other is rejected and handled as above.

### 6.3 Single source of truth

- Paddle is the authority for subscription state. The local subscription rows are a mirror of it.
- The rows change only from Paddle-originated data, through two paths:
  - a verified webhook;
  - the response to a Paddle API call made by the server. This is how Cashier's self-service methods work: `cancel()` calls Paddle and writes the returned end date to `ends_at`.
- Nothing sent by the browser changes the rows.
- Both paths go through the ordering rule in section 6.4.
- Access is derived only from these rows.
- Returning from checkout grants nothing. The page shows "a confirmar pagamento" and polls until the webhook has been processed.

### 6.4 Webhooks and ordering

Paddle delivers at least once and can deliver out of order. It names `event_id` for deduplication. Its `occurred_at` orders events but does not exist on API responses, so ordering here uses a version present on both paths.

- The signature is verified. Unsigned or wrongly signed requests are rejected.
- Deduplication is persistent: processed event IDs are stored under a unique constraint. A repeated event is acknowledged and changes nothing.
- Webhooks and API responses both carry the Paddle subscription entity. Each subscription row stores a provider-state version taken from that entity: its `updated_at` as set by Paddle. Local receipt time is never used as the version.
- Applying Paddle state, from either path, is one transaction that locks the subscription row, or the agent row when the subscription does not exist yet, and compares the incoming version with the stored one:
  - newer: the state is applied and the version stored;
  - equal: the state is the same provider state and applying it is a no-op;
  - older: the state is discarded.
- A webhook's event ID is recorded in the same transaction whatever the outcome.
- An older state arriving late does not change the row, even when it is handled concurrently with a newer one.
- That Paddle's `updated_at` changes on every state change and is comparable across webhooks and API responses is validated in Paddle's sandbox during the implementation plan. If it is not, the plan stops and this section is revised; no substitute is chosen silently.
- Whether Cashier's own webhook handling can be given these guarantees by extension, or must be replaced for subscription events, is settled in the implementation plan. The guarantees are the requirement.

### 6.5 Self-service

- The agent can switch plan, update the payment method and cancel.
- Cancelling takes effect at the end of the paid period, or at the end of the free month.
- Refunds are done by an admin in Paddle.

## 7. Access phases

The phase is computed on each request from the subscription rows and the lapse timestamp. Enforcement never depends on a scheduled job having run.

### 7.1 Lapse

There is one lapse transition: the subscription ends. The lapse timestamp is the subscription's `ends_at`, and `ends_at` is only ever written from Paddle data:

- **Cancelled by the agent:** the end of the paid period or of the free month, as returned by Paddle when the cancellation is scheduled.
- **Payment failure:** Paddle's cancellation time, when Paddle cancels the subscription after exhausting its payment retries. Paddle is configured to cancel, not pause, at the end of its retries.

While Paddle is retrying a failed payment the subscription is past due and the agent stays Active. This applies equally to the first charge after the free month. A failed charge on its own never starts the lapse.

- The retry window is bounded and explicitly configured in Paddle, ending in cancellation.
- While past due, the app shows "Pagamento pendente" with an action to update the payment method.
- Conversion is counted only from a successful payment, never from the Active phase.

The phase is derived from `ends_at` and the current time. No separate lapse flag is stored.

### 7.2 Phases

| Phase | When | Allowed |
| --- | --- | --- |
| No subscription | Signed up, never subscribed | Checkout only |
| Active | Free first month and paid period, including Paddle's payment retries | Everything |
| Read-only | Days 0 to 30 after lapse | View data; renew |
| Locked | Days 30 to 60 after lapse | Renew; see support contact |
| Marked for deletion | From day 60 after lapse | Renew; see support contact |

Rules:

- A single middleware on every agent route enforces the phase.
- In read-only, every mutation of agent data, every export and every file download is rejected server-side. Hiding controls in the interface is not the enforcement.
- Billing and authentication are explicit exceptions in every phase: opening a checkout, renewing, signing in and signing out stay available. They touch platform data only. Updating the payment method applies to a live subscription, so it is available while Active, including while past due.
- In locked and marked, no agent data is served.
- Renewal in any phase before erasure creates a new subscription. Once it is admitted, the phase follows the new subscription, full access is restored and the deletion mark is cleared. Renewal never overwrites the ended subscription's row; legitimate late Paddle updates to that row are still applied.
- Erasure of a marked account is performed only by an admin, manually. There is no automatic erasure.

### 7.3 Scheduled job

A daily job, on the system role:

- stamps the deletion mark on accounts reaching day 60;
- sends the lifecycle emails.

Lifecycle emails: on lapse, seven days before locking, on locking, seven days before marking, on marking (stating the erasure deadline), and seven days before the erasure deadline. Each email is sent once per lapse.

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
- The log is append-only at the database: the application role and the system role have only insert and select rights on it. Neither can update or delete, including through the admin connection.
- Entries identify the agent by an opaque internal identifier and never contain direct identifiers such as email, name or NIF, so erasure does not need to touch the log. The opaque identifier is pseudonymous, not anonymous: while an erasure record for that agent exists it can still be linked to a Paddle customer.

## 9. Data protection

### 9.1 Export

- An active agent can export their own data in the app.
- In read-only, locked and marked phases, the in-app export is unavailable. An admin produces the export from the admin panel on request, within the legal one-month limit.
- The export contains every agent-data table and any stored files. Each later spec adds its own data to the export.

### 9.2 Erasure

Erasure is performed by an admin, on the agent's request or for a marked account. It requires an explicit confirmation and is irreversible.

Cancelling at Paddle, deleting files and deleting rows cannot be one transaction, so erasure is a resumable process driven by an **erasure operation** record.

The erasure operation is stored independently of the agent, with no foreign key to it, so it survives the agent's deletion. It holds the opaque agent identifier, the agent's opaque storage prefix, the Paddle customer and subscription identifiers, the progress of each step, and any payments to reconcile. It holds no other data about the agent.

Steps:

1. **Open the operation.** In one transaction, create the erasure operation and put the agent in the erasing state, with an audit entry. From this point sign-in, checkout, renewal and every agent operation are refused, and existing sessions and tokens are revoked.
2. **Record it outside the database.** The operation is written durably to a store outside the database. No destructive step runs until this write is confirmed.
3. **Cancel at Paddle immediately.** Any live subscription is cancelled with immediate effect, not at period end. The step completes only when Paddle confirms the cancelled state.
4. **Delete stored files.** Every upload of the agent is first proven closed, so that no write can still succeed under the agent's storage prefix. Every object under the prefix is then deleted, and the prefix is verified empty before completion is marked in step 6. Elapsed time is never taken as proof that a write has stopped.
5. **Delete database rows** in one agent-scoped transaction on the system role: agent data, sessions, tokens, billing mirror rows and the agent. The same transaction marks the operation's data as deleted.
6. **Mark completion** in the off-database record.

Rules:

- Every step is idempotent. A failed erasure is retried from the admin panel and resumes at the first incomplete step, including after a failure between the two writes of steps 1 and 2 or of steps 5 and 6.
- An operation that is not complete is listed in the admin panel.
- Paddle keeps its own billing records as merchant of record.

Paddle activity during and after erasure:

- A checkout opened before erasure can complete after step 3. Ignoring its webhook would leave a billable subscription alive at Paddle.
- Webhooks run on the application role, which cannot read or write erasure operations. They never recreate an agent and never grant access.
- A webhook whose customer matches no agent, or matches an agent in the erasing state, is handed off: in the same transaction that records its event ID, the event is written to a billing handoff queue. The application role can only insert into that queue. Delivery is acknowledged to Paddle only after that transaction commits.
- A named system job, **erasure reconciliation**, consumes the queue on the system role. It alone matches events to erasure operations and acts on them. Each queue entry is processed idempotently and retried until done.
- If the event shows a live subscription, the job cancels it immediately at Paddle and retries until Paddle confirms.
- If the event shows a completed payment, the payment is recorded on the erasure operation as a payment to reconcile and flagged in the admin panel. Cancelling a subscription does not refund a completed payment: the refund is a separate admin action in Paddle, and the item stays open until an admin records it as handled.

Erasure-operation identifiers:

- Purpose: re-applying erasures after a restore, cancelling late subscriptions, and reconciling late payments.
- Access: the system role only, through the admin panel and the erasure and erasure reconciliation jobs. The application role has no access.
- Retention: the identifiers are purged only when every one of these conditions holds:
  - the operation is complete, including confirmed cancellation at Paddle;
  - every payment to reconcile is recorded as handled;
  - no retained backup can restore the account, meaning the backup retention period has passed since the rows were deleted;
  - no pending checkout of that agent is unexpired, and every Paddle subscription of that customer is confirmed cancelled;
  - at least 90 days have passed since completion.
- The 90 days are a proposed minimum, not a validated deletion deadline.

Safety does not depend on remembering an erased customer forever. After the identifiers are purged, a late Paddle event is handled by the general rules for an unknown customer:

- A webhook never creates an agent. Agents are created only by sign-up.
- An event for a customer that matches no agent goes through the same handoff queue. With no agent, no pending checkout and no erasure operation to match, the erasure reconciliation job treats the subscription as rejected: it cancels it at Paddle, retries until confirmed, and flags it in the admin panel with any completed payment to reconcile.
- These rules act only on subscriptions for Agentimo's own Paddle prices. The allowlist includes retired Agentimo prices, not only those currently offered. Events for any other price are acknowledged and left alone.

### 9.3 Retention

- Agent data is kept while the account exists.
- After the deletion mark, erasure stays a manual admin action with a default deadline: a marked account is erased within 30 days of being marked, that is by day 90 after lapse. Manual means an admin performs it, not that retention is open-ended.
- The agent is told the deadline in advance: in the email sent on marking, and again seven days before the deadline.
- An exception keeps a marked account beyond the deadline. It requires:
  - a specific necessity, chosen from a fixed list (an open dispute or legal claim, a pending data-access request, a written request from the agent) with a written justification;
  - the data retained, limited to what that necessity needs. Everything else is erased at the deadline;
  - a next review date at most 30 days ahead.
- An open refund or payment reconciliation is not a ground for an exception. The account is erased on schedule and the reconciliation continues on the erasure operation, which holds what it needs.
- At the review date the exception ends unless it is renewed, and a renewal must state why the same necessity still holds. An exception with no current necessity cannot be renewed, and the account is erased.
- These numbers are operational product choices. They are not a confirmation of legal retention compliance.
- The admin panel lists marked accounts with their deadline and shows the overdue ones.
- The privacy policy states the deadline and the exception rule.
- Backups are daily, encrypted, and kept for 30 days. Erased data leaves backups as they rotate. Restore is tested.

### 9.4 Restore

A restored backup can reintroduce erased accounts, revoked sessions and stale subscription state. After a restore, and before the service is reopened:

- every erasure operation retained in the off-database record is reconciled against the restored database, whatever its opening date and whether complete or not. An operation opened before the backup and completed after it is re-applied like any other;
- all sessions and pending magic-link tokens are revoked;
- subscription rows are resynchronised from Paddle.

### 9.5 Legal pages

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
- The deployment checklist records Paddle's payment-retry duration and its terminal action, which must be cancellation.

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
- After an admin changes an agent's email, a session and a magic link issued before the change no longer work.

Billing:

- Bad signatures are rejected.
- A replayed event changes nothing.
- An older event arriving late does not overwrite newer state.
- Two events for the same subscription processed concurrently leave the state of the newer one.
- A self-service cancellation writes `ends_at` from Paddle's API response and is not undone by a webhook carrying an older provider version.
- A subscription on a price the agent was not authorised for is rejected, cancelled and grants no access.
- A subscription whose update event arrives before its creation event grants no access until admitted, and is admitted or rejected by the same rules.
- A pending checkout cannot admit two subscriptions.
- A checkout completed before its expiry is admitted when its webhook arrives after the expiry.
- A state with an equal provider version is a no-op; an older one is discarded; local receipt time never decides.
- An agent who has had a subscription cannot obtain the trial price by manipulating the checkout.
- Two simultaneous checkouts by one agent end with one admitted live subscription; the other is mirrored as rejected.
- A rejected subscription whose cancellation fails at Paddle stays mirrored and is retried until confirmed.
- A second admitted live subscription for one agent is refused by the database.
- The checkout return grants no access before the webhook.
- A new agent on the monthly plan gets the trial price and full access with no charge.
- An agent who has had any subscription gets the price without trial.
- A free month cancelled by the agent lapses when the month ends.
- A failed charge, including the first one after the free month, leaves the agent Active while Paddle retries.
- When Paddle cancels after its retries, the lapse starts at Paddle's cancellation time.
- A past-due agent sees "Pagamento pendente" and can update the payment method.
- A late Paddle update to an ended subscription is applied to that row and does not affect the new one.

Phases:

- Boundaries at days 29, 30, 59 and 60, using time travel.
- A test walks every agent route and proves it sits behind the phase middleware.
- In read-only, every agent-data mutation, export and download route is rejected.
- In each lapsed phase a real renewal succeeds end to end: checkout opens, the webhook is applied, access is restored and the marks are cleared.
- Updating the payment method works while the subscription is past due.
- Each lifecycle email is sent once.

Admin:

- An agent session cannot reach the panel; an admin session cannot reach the agent app.
- Two-factor is required.
- Every action writes an audit entry.
- Direct SQL as the application role and as the system role cannot update or delete an audit entry.
- Erasure leaves no rows or files of the agent behind.
- An erasure interrupted after each step, and between the two writes of steps 1 and 2 and of steps 5 and 6, resumes and completes when retried.
- No destructive step runs before the off-database record is confirmed.
- The erasure operation survives the deletion of the agent.
- An agent in the erasing state cannot sign in, open a checkout or renew.
- A late webhook for an erased customer creates no agent and grants no access.
- The application role cannot read or write erasure operations and can only insert into the handoff queue.
- A handed-off event is committed to the queue before delivery is acknowledged, and survives a crash before the system job runs.
- A subscription that becomes live during or after erasure is cancelled at Paddle, idempotently.
- A payment completed during or after erasure is recorded for reconciliation and stays flagged until an admin records the refund as handled.
- Erasure-operation identifiers are not purged while any purge condition is unmet: an unreconciled payment, a backup still inside its retention period, an unexpired pending checkout, an unconfirmed cancellation, or fewer than 90 days since completion.
- After the identifiers are purged, a late webhook for that customer creates no agent and grants no access; a live subscription in it is rejected, cancelled and flagged.
- An event for a price that is not Agentimo's is acknowledged and nothing is cancelled. A retired Agentimo price is still covered.
- After a simulated restore, reconciling the off-database record removes the erased agent again, old sessions are rejected, and subscription state matches Paddle.
- Restore timeline: an operation opened on Monday, a backup taken on Tuesday, deletion completed on Wednesday. Restoring Tuesday's backup re-applies the operation and the data is gone again.
- Marked accounts past their deadline are listed.
- An exception requires a listed necessity, a justification, the data retained and a review date at most 30 days ahead, and ends at that date unless renewed.
- Under an exception, data outside its stated scope is erased at the deadline.
- An open refund does not block erasure.
- The deadline emails are sent on marking and seven days before the deadline.

End to end:

- One manual pass against Paddle's sandbox: sign up, start the free month, convert to paid, cancel, lapse, renew without a second free month.

## 12. Implementation gates

Two facts about Paddle must be validated in its sandbox before the dependent work is built. Each is a stop condition: if it fails, the plan stops and this spec is revised.

- Paddle's subscription `updated_at` changes on every state change and is comparable across webhooks and API responses (section 6.4).
- The pending checkout's identifier is present on the subscription data of every relevant event (section 6.2).

## 13. Confirmed assumptions

- Displayed prices include VAT.
- Hosting is in an EU region.
- Backups are daily, encrypted and kept for 30 days.
