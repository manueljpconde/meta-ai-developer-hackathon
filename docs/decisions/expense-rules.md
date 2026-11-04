# Expense rules (owner hotfix 1a, 2026-11-04)

Source: item 6 C6–C9 and the owner's rulings of 2026-11-04.

- An expense has a description, an amount in cents (> 0), a date (any past or future date), paid or planned, and optionally one of the agent's own deals. Every row carries its tenant; every query is scoped by it.
- Expenses belong to months, not deals. The money a month subtracts (`engine.calc.month_expenses`):
  - past month: the sum of the expenses recorded in it (paid and planned);
  - future month: the Settings estimate plus the planned expenses in it;
  - current month: the larger of the expenses recorded so far and the estimate.
- The past/current/future split always uses the real current month (Lisbon), never the dashboard window.
- A month with no deal still carries its expenses (really yours may be negative). Month cards exist only for months with deals; the dashboard and the 3-month strip count every month.
- Each stage of a month is computed before expenses; the month's expenses are subtracted once.
- `deals.expenses_cents` stays in the schema (rollback to the previous commit keeps working) but no forecast reads it.
- No backfill: the estimate is never turned into recorded expenses. Verified before deploy that no tenant has an active deal in a past month.
- Receipts are not used: "Recebido" shows the active deals whose escritura fell in that past month (owner, 2026-11-04: "não quero gerir recebimentos").
- Deleting a deal unlinks its expenses; deleting the account deletes them.
