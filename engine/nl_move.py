"""Natural-language move input for the Cash-flow Scenario Assistant.

Move operation only: one typed sentence such as "Move the Benfica
payment to January" is turned into a structured move (deal reference,
payment, target month) through an interpretation client, then passed
to the existing ``engine.move.move_payment`` and shown as the
before/after forecast. An ambiguous sentence, an unknown deal or
payment, or a refusal from the engine produces one focused question
instead of guessing; a model failure is an error, never a guess.
Stored records are never changed: the engine call is pure and the
given records are only read.
"""

import unicodedata

from engine.calc import calc_month
from engine.move import MONTH_RE, move_payment

RATE_KEYS = ("iva_rate", "retencao_rate", "irs_rate", "ss_rate")

PT_MONTH_NAMES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
EN_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)


def normalize_name(name):
    """Compare names ignoring case and accents (Q4 fallback).

    Unicode NFKD decomposition with combining marks stripped, then
    casefold, via the standard library only.
    """
    decomposed = unicodedata.normalize("NFKD", name or "")
    stripped = "".join(
        char for char in decomposed if not unicodedata.combining(char))
    return stripped.casefold()


def _month_index(name):
    """Month index 1-12 for a Portuguese or English name, else None."""
    wanted = normalize_name(name)
    for index, candidate in enumerate(PT_MONTH_NAMES, start=1):
        if normalize_name(candidate) == wanted:
            return index
    for index, candidate in enumerate(EN_MONTH_NAMES, start=1):
        if normalize_name(candidate) == wanted:
            return index
    return None


def resolve_month_reference(text, current_month):
    """Resolve a month reference to ``YYYY-MM`` (Q5 rule), else None.

    A bare month name means its next occurrence from the current
    month: the same year when its index is at or after the current
    month index, otherwise the next year. An explicit ``YYYY-MM``
    passes through only when it matches the engine month shape.
    """
    if isinstance(text, str) and MONTH_RE.fullmatch(text):
        return text
    if (not isinstance(text, str) or not MONTH_RE.fullmatch(
            current_month or "")):
        return None
    index = _month_index(text.strip())
    if index is None:
        return None
    year, current_index = int(current_month[:4]), int(current_month[5:7])
    if index < current_index:
        year += 1
    return "%04d-%02d" % (year, index)


def _resolve_deal(deal, records):
    """Resolve wording to registered deals by normalized name (Q4)."""
    wanted = normalize_name(deal)
    return [entry for entry in records
            if normalize_name(entry.get("deal", "")) == wanted]


def _part_for(entry):
    """Build an engine part dict from a record, leaving it untouched."""
    part = {"part_base": entry["part_base"]}
    for key in RATE_KEYS:
        if key in entry:
            part[key] = entry[key]
    if "other_rates" in entry:
        part["other_rates"] = entry["other_rates"]
    return part


def _forecast(records, expenses_cents):
    """Aggregate the unpaid expected money by month, via engine.calc."""
    months = {}
    for entry in records:
        if entry.get("received", False):
            continue
        months.setdefault(entry["month"], []).append(_part_for(entry))
    return {
        month: calc_month(parts, expenses=expenses_cents)
        for month, parts in sorted(months.items())
    }


def plan_nl_move(sentence, records, current_month, interpret,
                 expenses_cents=0):
    """Plan one move from a sentence, without changing stored records.

    ``interpret`` turns the sentence into a dict: either a move with
    ``deal``, ``payment`` and ``target_month``, or ``{"question":
    ...}`` when the sentence itself is ambiguous. The result is one
    of three shapes: ``{"status": "moved", "moved": ..., "before":
    ..., "after": ...}`` for a clear move, ``{"status": "question",
    "question": ...}`` asking one focused question instead of
    guessing, or ``{"status": "error", "message": ...}`` when the
    model call or its answer failed.
    """
    if not isinstance(sentence, str) or not sentence.strip():
        return {
            "status": "question",
            "question": "Which payment should I move, and to which month?",
        }
    try:
        reading = interpret(sentence)
    except Exception as exc:
        return {
            "status": "error",
            "message": (str(exc)
                        or "The model call failed, so nothing was moved."),
        }
    if (isinstance(reading, dict)
            and isinstance(reading.get("question"), str)
            and reading["question"].strip()):
        return {"status": "question",
                "question": reading["question"].strip()}
    if not isinstance(reading, dict):
        return {
            "status": "error",
            "message": "The model answer could not be read, "
                       "so nothing was moved.",
        }
    deal = reading.get("deal")
    payment = reading.get("payment")
    target = reading.get("target_month")
    if (not isinstance(deal, str) or not deal
            or not isinstance(payment, str) or not payment):
        return {
            "status": "question",
            "question": "Which payment should I move?",
        }
    if isinstance(target, str) and not MONTH_RE.fullmatch(target):
        resolved = resolve_month_reference(target, current_month)
        target = resolved if resolved is not None else target
    if not isinstance(target, str) or not MONTH_RE.fullmatch(target):
        return {
            "status": "question",
            "question": ("Which month should the %s %s payment move to?"
                         % (deal, payment)),
        }
    if isinstance(records, (list, tuple)):
        resolved = _resolve_deal(deal, records)
        if len(resolved) == 1:
            deal = resolved[0]["deal"]
        elif len(resolved) > 1:
            names = ", ".join(
                "%s (%s)" % (entry["deal"], entry["month"])
                for entry in resolved)
            return {
                "status": "question",
                "question": ("Which %s payment did you mean: %s?"
                             % (deal, names)),
            }
        elif records:
            names = ", ".join(
                "%s (%s)" % (entry["deal"], entry.get("month", ""))
                for entry in records)
            return {
                "status": "question",
                "question": ("%s was not found. Registered deals: %s. "
                             "Which payment should I move?"
                             % (deal, names)),
            }
    try:
        outcome = move_payment(
            records,
            {"deal": deal, "payment": payment, "target_month": target},
            current_month,
            expenses_cents=expenses_cents,
        )
    except ValueError as exc:
        return {"status": "question", "question": str(exc)}
    return {
        "status": "moved",
        "moved": outcome["moved"],
        "before": _forecast(records, expenses_cents),
        "after": outcome["forecast"],
    }
