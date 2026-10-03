# Product core — design

Date: 2026-10-03

Status: design approved in conversation; awaiting written-spec review

Tracking: [issue #3](https://github.com/CrmWare/propware-agentimo/issues/3)

Builds on: `2026-10-03-foundation-design.md` ([issue #2](https://github.com/CrmWare/propware-agentimo/issues/2))

## 1. Purpose

The product core delivers the promise of the MVP: the agent sees how much will land in their account, how much of it must be protected, and how much is really theirs.

It covers the four MVP features (negócios and commissions, financial profile, expenses, forecast) and the onboarding that produces the first useful answer from one real negócio.

## 2. Scope

In scope:

- Financial profile.
- Negócios and payment parts.
- Settlements (receiving a payment part).
- Expenses and recurring expense rules.
- The calculation engine.
- Forecast and history.
- Onboarding.

Out of scope:

- Deductible IVA.
- Fixed-amount reserves.
- Effective-dated profile settings.
- Currencies other than EUR.
- Probability weighting of scenarios.
- Imports from CRMs or banks.
- Any official tax or Segurança Social calculation. Every rate is the agent's own setting.
- Receipts (receipt assistant spec).

## 3. Global invariants

- EUR only.
- Money is integer cents. Floating-point arithmetic is prohibited for money.
- Rounding is half-up to the cent, applied at the component boundaries defined in section 5.
- Reserve rates are between 0% and 100%.
- IVA and retenção settings each hold applicability and a rate, not only a boolean.
- Every entity is ownership-scoped to one agent.
- Agency details are copied onto the negócio at creation and never resolved dynamically from profile defaults.

## 4. Data model

### 4.1 Financial profile

One per agent.

- Default agent share rate, used to pre-fill new negócios.
- Default agency name and NIF, copied onto each new negócio.
- Agent's NIF.
- IVA setting: applicability, rate, and the legal mention when exempt.
- Retenção setting: applicability and rate.
- Reserve rates: IRS, Segurança Social, and any number of named others.

The agent's NIF and the agency NIF are optional here. Only the receipt assistant requires them.

The Segurança Social reserve is labelled an estimate wherever it is shown.

The profile holds percentages only. Fixed-amount reserves are out of scope. Recurring expenses are for genuine recurring operating costs only, never for reserves.

### 4.2 Negócio

- Name.
- `agency_commission_base`: the agency's commission, without IVA.
- `agent_share_rate`: the agent's percentage for this negócio.
- `agent_commission_base`: derived, `round(agency_commission_base × agent_share_rate)`.
- Agency name and NIF.
- Stage: `potencial`, `provável`, `confirmado` or `perdido`.
- Archived flag.

Settlement state is derived, never stored:

| Settlement state | Condition |
| --- | --- |
| `unpaid` | Zero valid settlements |
| `partially_received` | At least one valid settlement and at least one active expected part |
| `received` | At least one valid settlement and zero active expected parts |

The three states are mutually exclusive. A negócio whose parts are all cancelled, with no settlement, is `unpaid`.

"Recebido" is a settlement badge, not a stage.

### 4.3 Payment part

- Negócio reference.
- `expected_base`, without IVA.
- Expected month.
- Stored status: `expected` or `cancelled`.
- Cancellation reason when cancelled: `negocio_lost`, `manual` or `superseded`.
  - `negocio_lost` and `manual` mean the entitlement was given up. The part's `expected_base` counts as written off in the total invariant and never appears in a forecast.
  - `superseded` means the part was replaced by other parts in a split or redistribution. It counts nowhere.

A part is **received** when it has a current valid settlement. "Received" is derived from the settlement and is never stored on the part.

A part with a settlement keeps its `expected_base` and expected month unchanged, so variance against the actual remains visible.

### 4.4 Settlement

An append-only record that a payment part was received.

- Payment-part reference.
- Actual payment date.
- `actual_base`: the actual agent-share amount, without IVA.
- Optional observed bank inflow, and the acknowledged difference.
- Frozen engine inputs: the IVA, retenção and reserve settings used.
- Frozen engine outputs: IVA, retenção, expected bank inflow, each protected amount, protected total, and the available amount before expenses.
- Engine version.
- Confirmation timestamp.
- Idempotency key.
- Optional `supersedes_settlement_id`.

The **current valid settlement** of a part is the one that no other settlement supersedes. Earlier ones stay on record.

### 4.5 Commission adjustment

An append-only record that the commission actually due differs from `agent_commission_base`, created only as the explicit resolution of a difference when a part is received or a settlement is corrected (section 6.3).

- Negócio reference.
- Settlement reference: the settlement whose difference it resolves.
- Signed amount in cents: negative when the commission was smaller, positive when it was larger.

Only adjustments that belong to a current valid settlement count. When a settlement is superseded, its adjustments stop counting.

The negócio's **effective commission** is `agent_commission_base` plus its counting adjustments. It is what the interface shows as the commission once any adjustment exists.

### 4.6 Expenses

**One-off expense**

- Description.
- Expected date and expected gross amount.
- Optional negócio link, for attribution only.

**Recurring expense rule**

- Description, expected gross amount, monthly recurrence, start month and optional end month.
- Optional negócio link.
- A rule is a forecast rule. Its occurrences are computed on read; no monthly rows are stored for them.

**Paid-expense record**

An append-only record that an expense was paid.

- Reference to the one-off expense, or to the rule and the month of the occurrence. Records for one-off expenses and records for recurring occurrences are stored separately, so each kind has a non-null item identity that the database can constrain.
- Actual date and actual gross amount.
- Idempotency key.
- Optional `supersedes_id`.

An expense or occurrence is **paid** when it has a current valid paid-expense record. "Paid" is derived and never stored on the expense.

**Occurrence states**, all derived:

| State | Condition |
| --- | --- |
| Expected | The month has not passed and no paid record exists |
| Paid | A current valid paid record exists |
| Skipped | The agent skipped this occurrence |
| Unreviewed | The month has passed with no paid record and no skip |

Skips are stored as one row per rule and month.

Skip and payment are mutually exclusive for the same rule and month, enforced in the database:

- A skip cannot be recorded for an occurrence that has a paid record.
- A paid record cannot be written for a skipped occurrence.
- "Unskip and confirm" is one explicit action that removes the skip and writes the paid record in the same transaction.
- A paid occurrence is never skipped. A wrong payment is corrected by replacement.

A negócio-linked expense stays counted when the negócio becomes `perdido`. The money was still spent.

## 5. Calculation engine

A pure, versioned function. It is the only place this arithmetic exists; the forecast and the receipt assistant both call it.

### 5.1 Per payment part

```text
iva           = round(part_base × iva_rate)
retencao      = round(part_base × retencao_rate)

bank_inflow   = part_base + iva − retencao

irs_target    = round(part_base × irs_reserve_rate)
irs_reserve   = max(irs_target − retencao, 0)

ss_reserve    = round(part_base × ss_reserve_rate)
other_reserve = round(part_base × other_rate)        (one per named reserve)

protected_money = iva + irs_reserve + ss_reserve + sum(other_reserves)
```

- `part_base` is the `expected_base` for an expected part and the frozen `actual_base` for a received part.
- A rate that is not applicable is zero.
- `iva` inside `protected_money` is the conservative IVA reserve. It is never labelled as IVA owed.
- Every component is calculated and rounded independently per part.

### 5.2 Per month

- Monthly figures sum the cent-denominated components of that month's parts. They are never re-rounded.
- `really_available = bank_inflow − protected_money − expenses`, with expenses at gross cash amount.

### 5.3 Sources of values

- Expected parts: the current profile.
- Received parts: the frozen settlement. The engine is not re-run for them.

### 5.4 Versioning

- The engine version is stored on every settlement.
- Changing engine logic bumps the version.
- Existing settlements are never recomputed.

### 5.5 The four amounts

| Amount | Label | Definition |
| --- | --- | --- |
| Commission earned | "Comissão" | Sum of part bases, without IVA |
| Expected bank inflow | "Entrará na conta" | Sum of `bank_inflow` |
| Protected money | "Dinheiro a proteger" | Sum of `protected_money`, shown broken down |
| Really available | "É realmente teu" | Section 5.2 |

"Entrará na conta" and "é realmente teu" are never the same number under the same label.

## 6. Invariants on payment parts

### 6.1 Total invariant

```text
agent_commission_base
+ sum(counting commission adjustments)
=
  sum(actual_base of current valid settlements)        received
+ sum(expected_base of active expected parts)          outstanding
+ sum(expected_base of parts cancelled as
      negocio_lost or manual)                          written off
```

- An active expected part is one with status `expected` and no settlement.
- Parts cancelled as `superseded` are excluded.
- Reconciliation and forecast inclusion are separate. Written-off parts take part in this invariant and in no forecast. Only outstanding parts are forecast money.

Worked cases, for a negócio with an agent share of 1,000.00 EUR:

| Event | Received | Outstanding | Written off | Adjustments | Holds |
| --- | --- | --- | --- | --- | --- |
| Created | 0 | 1,000 | 0 | 0 | 1,000 = 1,000 |
| Marked perdido, nothing received | 0 | 0 | 1,000 | 0 | 1,000 = 1,000 |
| 400 received, then perdido | 400 | 0 | 600 | 0 | 1,000 = 1,000 |
| Reopened after that | 400 | 600 | 0 | 0 | 1,000 = 1,000 |
| 900 received on the only part, commission was smaller | 900 | 0 | 0 | −100 | 900 = 900 |
| 900 received on the only part, 100 still due | 900 | 100 | 0 | 0 | 1,000 = 1,000 |

### 6.2 Changing a negócio

When `agency_commission_base` or `agent_share_rate` changes:

- Received actual bases remain untouched.
- The remaining difference is distributed across active expected parts.
- Any cent remainder goes to the last expected part.
- When there is no active expected part and the difference is positive, the change requires an expected month and creates a new expected part for the difference.
- A new total below the received actual total is refused. The agent must make an explicit correction first.
- Written-off parts and adjustments are untouched by a commission change.
- A commission change is refused on a `perdido` negócio. It must be reopened first.
- A commission change that would create an outstanding balance is refused on an archived negócio. It must be unarchived first.

### 6.3 Resolving a difference on receipt

Receiving an `actual_base` that differs from the part's `expected_base`, or correcting a settlement to a different `actual_base`, leaves a gap in the total invariant. The gap is never resolved implicitly. The agent makes an explicit choice, and the settlement and its resolution are written in the same transaction.

When less was received than expected:

- **"Ainda falta receber":** the difference becomes a new expected part. An expected month is required.
- **"A comissão foi menor":** a negative commission adjustment for the difference.

When more was received than expected:

- **"Antecipa valores em falta":** the excess is taken from the other active expected parts, the last one first. Any excess beyond the outstanding balance must be resolved as a larger commission.
- **"A comissão foi maior":** a positive commission adjustment for the excess.

When a settlement is corrected:

- The replacement's adjustments replace those of the superseded settlement, which stop counting.
- The same explicit choice is made for whatever gap the new `actual_base` leaves, against the parts as they stand at that moment.

No operation commits with a gap. A request that does not carry a resolution for its difference is refused.

### 6.4 Enforcement

- The total invariant is enforced in the database by a deferred constraint trigger that verifies it at commit.
- Every mutation that can affect the total locks the negócio row first, in the same order: split, edit a part, receive, correct, mark as perdido, reopen, change commission, archive and unarchive.
- The same trigger enforces that an archived negócio has no active expected part, on every mutation and not only at the moment of archiving.

## 7. Scenarios, forecast and history

### 7.1 Scenarios

Cumulative, with no probability weighting.

| Scenario | Contains |
| --- | --- |
| Confirmado | All settlements, plus expected parts of `confirmado` negócios |
| Provável | Confirmado, plus expected parts of `provável` negócios |
| Total | Provável, plus expected parts of `potencial` negócios |

- Received amounts are scenario-independent.
- Cancelled parts are in none. A `perdido` or archived negócio contributes no expected parts.
- Valid settlements and paid expenses remain in actuals and history whatever the negócio's later stage or archive state.
- Expenses are identical in all three.

### 7.2 Forecast

- Range: the current month and the next eleven.
- Each month shows the four amounts for the selected scenario.
- Month assignment: expected items by expected month or date; received and paid items by actual date.

### 7.3 History

- Range: the previous eleven months and the current month.
- Compares the expected values retained on received parts with their frozen settlement.
- Rescheduling an unpaid part does not create a historical actual.
- Unreviewed occurrences are included at the expected amount, labelled estimated, and excluded from confirmed-actual totals.

### 7.4 Overdue items

An expected part or one-off expense whose expected month has passed, without a settlement or paid record:

- keeps its original expected month;
- is carried into the current month of the forecast exactly once;
- is shown as "Em atraso desde <mês>" and "Incluído em <mês atual>";
- may appear in history as a missed expectation in its original month;
- never contributes twice to forecast totals.

## 8. Flows

### 8.1 Onboarding

After subscribing:

1. Usual share rate and agency name.
2. IVA and retenção settings, then reserve rates. Every rate is entered by the agent. Zero is allowed. No value is suggested.
3. Recurring expenses. Skippable.
4. One real negócio. Required.
5. The forecast for that negócio is shown immediately.

### 8.2 Negócio

- **Create:** name, agency commission, share rate (pre-filled), expected month, stage. One part is created for the full agent share. The target is under 60 seconds.
- **Split:** opens the schedule to add parts and move amounts between them.
- **Mark as perdido:** active expected parts become `cancelled` with reason `negocio_lost`, which moves their amount from outstanding to written off, so the total invariant holds. Settlements remain. Received amounts stay in history.
- **Reopen:** only parts cancelled with reason `negocio_lost` return to `expected`. Parts cancelled as `manual` or `superseded` are not revived.
- **Delete:** only a negócio with no settlements, no expense links and no other history.
- **Archive:** any other negócio, and only when it has no active expected part. Archiving transactionally rejects a negócio that still holds forecast money. An archived negócio therefore contributes no expected money to the forecast by construction; its settlements stay in actuals and history.
- **Unarchive:** an explicit action. Any change that would give an archived negócio an outstanding balance (a commission increase, a reopening, a shortfall resolved as still due) is refused until it is unarchived.

### 8.3 Receiving a part

Receiving is a confirmation boundary.

1. The screen shows the calculated bank inflow for the part.
2. The agent confirms the actual payment date and the `actual_base` without IVA. The `actual_base` is the authoritative input.
3. Optionally the agent enters the observed bank amount. It never drives the calculation. The screen shows calculated inflow, observed inflow and the difference, and a non-zero difference must be acknowledged.
4. If the `actual_base` differs from the part's `expected_base`, the agent chooses how the difference is resolved (section 6.3).
5. On confirmation the settlement and its resolution are written in one transaction, with frozen inputs, outputs and engine version.

Rules:

- A part can be received only on a `confirmado` negócio. On another stage the agent is offered one explicit compound action, "Confirmar negócio e registar recebimento". The stage is never changed silently.
- After confirmation, profile changes never alter the settlement.
- A correction is an explicit replacement: a new settlement that supersedes the previous one, for the same payment part, with its own resolution of any difference.

### 8.4 Expenses

- **One-off:** entered as expected or as already paid. Expected expenses are freely editable.
- **Recurring:** a rule. Confirming an occurrence writes that month's paid record.
- **Unreviewed occurrences:** low-friction actions are confirm amount, correct amount, skip this occurrence, and confirm all unchanged occurrences. Only confirmation writes a paid record.
- **Correcting a paid expense:** an explicit replacement that supersedes the previous record. The original stays on record and the latest valid one drives calculations.

## 9. Isolation and integrity

### 9.1 Isolation

- Every table in this spec is agent data. Both foundation layers apply: the owner trait and forced row-level security.
- Ownership columns are `NOT NULL`, cannot be changed by the application role, and are protected by row-level security `WITH CHECK`.
- Child tables (parts, settlements, expenses, rules, paid records, skips) carry the owner column themselves.
- A composite foreign key guarantees a child's owner equals its parent's. Each parent has a unique constraint on `(id, owner_id)` to support it.

### 9.2 Append-only records

- The application role has only insert and select rights on settlements, commission adjustments and paid-expense records.
- Erasure goes through the system role.

### 9.3 Uniqueness

- One original settlement per payment part.
- One direct replacement per record, for settlements and for paid-expense records.
- A replacement must reference an existing predecessor of the same financial item: a settlement can supersede only a settlement of the same payment part; a paid record can supersede only a paid record of the same one-off expense, or of the same rule and month. This is enforced in the database by composite foreign keys that include the item identity, not only by ownership.
- One original paid record per one-off expense.
- One original paid record per recurrence rule and month.
- No skip and paid record for the same rule and month, enforced by a constraint trigger across the two tables.
- Skip, confirm, unskip, and unskip-and-confirm are serialised per recurrence rule: each locks the rule row before checking and writing, and the constraint trigger takes the same lock, so the serialisation holds for any code path. Two concurrent transactions can never both see "no conflicting row" and both succeed.

### 9.4 Idempotency

- Every operation that writes a settlement or a paid-expense record carries a client-generated idempotency key, unique per agent and operation.
- A fingerprint of the request payload is stored with the key.
- A repeated request with the same key and the same payload returns the previously created record. It does not return an error and does not create a second record.
- The same key with a different payload returns a conflict. It never returns the earlier, unrelated result.

### 9.5 Phase guard

- All HTTP routes sit behind the foundation's phase middleware.
- Every mutation service also calls the shared phase guard, so a write is refused in the read-only, locked and marked phases whatever its entry point: HTTP, queue job or command.
- The product core has no non-HTTP writers in the pilot. The guard in the services exists so that later writers, including the receipt assistant, cannot bypass it.

### 9.6 Export and erasure

- The agent's export includes every table in this spec, superseded records included.
- Erasure runs as one agent-scoped transaction on the system role and removes all of it.

## 10. Testing

Tests are written before implementation.

Engine:

- A table of settings: IVA applicable and exempt, retenção applicable and not, reserve rates including zero.
- A real Portal receipt as a fixture: the engine reproduces its figures.
- Half-up rounding at each component boundary.
- `irs_reserve` floors at zero when retenção exceeds the target.

Invariants:

- Property tests apply random sequences of split, edit, receive, lose, reopen, correct and commission change, then assert the total invariant and that settlements never change.
- The cent remainder goes to the last expected part.
- A new total below the received total is refused.
- Increasing a fully received negócio requires an expected month and creates a new part.
- The three settlement states are mutually exclusive, including for a negócio with all parts cancelled.
- The total invariant holds through: perdido with nothing received, partial receipt then perdido, and reopening after each.
- Receiving less than expected is refused without a resolution; each resolution (still due, smaller commission) commits with the invariant holding.
- Receiving more than expected: taken from later parts, the last first; excess beyond the outstanding balance requires a larger commission.
- Correcting a settlement to a different amount stops its old adjustments counting and requires a new resolution.
- A commission change is refused on a perdido negócio, and leaves written-off parts and adjustments untouched.

Concurrency and idempotency:

- Concurrent receive against split, against lose, and against commission edit.
- Duplicate requests with the same idempotency key and payload return the same record.
- The same idempotency key with a different payload returns a conflict.
- A double submit without a matching key is rejected by the uniqueness constraints.

Snapshots and corrections:

- Profile changes leave settlements unchanged.
- Correction chains select exactly one current record, for settlements and for paid expenses.
- A replacement that references a record of a different payment part, expense or occurrence, or a predecessor that does not exist, is rejected by the database.
- A changed engine version does not recompute existing settlements.

Scenarios and ranges:

- The cumulative ladder.
- Forecast range against history range.
- An overdue item is counted exactly once.
- Unreviewed occurrences are labelled estimated and excluded from confirmed actuals.

Negócio lifecycle:

- Perdido cancels expected parts and keeps settlements.
- Settlements and paid expenses of a perdido or archived negócio still appear in actuals and history.
- Reopening revives only `negocio_lost` parts.
- Archive is rejected while forecast money exists.
- A commission increase, a reopening, and a shortfall resolved as still due are each refused on an archived negócio until it is unarchived; the database rejects an archived negócio with an active expected part from any path.
- Delete is rejected when history exists.
- Receiving on a non-confirmado negócio requires the compound action.

Expenses:

- Occurrence states, the bulk confirm, skips and replacements.
- An occurrence cannot be both skipped and paid; "unskip and confirm" is atomic.
- A skip and a payment for the same occurrence submitted concurrently end with exactly one of them.
- A one-off expense cannot have two original paid records.
- A linked expense is still counted after the negócio is perdido.

Database guards:

- The application role cannot update or delete a settlement, a commission adjustment or a paid-expense record.
- Cross-owner child insertion is rejected.
- Both isolation layers hold for every table.
- The deferred trigger rejects a commit that breaks the total invariant, including from a path that bypasses the services.

Phase guard:

- Every mutation service refuses writes in the read-only, locked and marked phases.

Export and erasure:

- The export is complete, including superseded records.
- Erasure leaves no rows behind.

Architecture:

- Money moves only through the cents type; no floating point.

Onboarding:

- The forecast appears after the first negócio.
- The under-60-seconds criterion for creating a negócio is checked by hand.

## 11. Changes to other documents

Separate changes, not part of this spec:

- **Receipt assistant spec:** its draft uses this engine; its base comes from the received part's settlement; "missing receipts" compares against settlements.
- **`docs/mvp-analysis.md`:** §4 (payment parts, perdido, cash-aware forecast) and §6 (receipts, per issue #1). §7 is affected by the free first month decided in issue #2.
