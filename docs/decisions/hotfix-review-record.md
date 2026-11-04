# Hotfix branch review record (2026-11-04)

This item reviews the owner's live hotfixes rather than building new work. The branch
`wi/wi-01M6KAQHFERBVK2GK47WWMY0XA` holds the 12 hotfix commits on top of the previous
item's head `d770f3c`, ending at `1598f8d`. The writer does not rewrite them; this file
is the only addition, made because the authority refuses to record the same head as a
result twice (the identical head was already submitted by the earlier review item for
the same hotfixes). The owner approved a docs-only commit for that case.

What the range `d770f3c..1598f8d` contains (25 files, 1 740 insertions, 119 deletions):

- Recorded expenses: an expenses table, the Despesas page and the monthly expense rule
  (details in `expense-rules.md`).
- Previsão dashboard: headline, window controls, the Fechado and Previsto blocks and a
  really-yours-per-month chart, with negative months flagged.
- Expense by voice, through the one Falar button, and per-deal figures.
- Voice and sign-in fixes: Safari speech capture and recovery, page language, one Falar
  button per width, question-shaped updates accepting an update's field names, and
  sign-in links changing nothing on GET.

The review of these hotfixes checks against no criteria (owner ruling): QA, business
and code review examine the diff as recorded. The merge to main is the owner's, through
the factory's normal path after result approval.
