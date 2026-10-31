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
                 expenses_cents=0, lang="en"):
    """Plan one move from a sentence, without changing stored records.

    ``interpret`` turns the sentence into a dict: either a move with
    ``deal`` and ``target_month`` plus, optionally, ``payment``, or
    a question dict when the sentence itself is ambiguous. The result
    is one of three shapes: a moved result with ``moved``,
    ``before`` and ``after`` for a clear move, a question result
    asking one focused question instead of guessing, or an error
    result when the model call or its answer failed.

    When the matched deal has exactly one unpaid payment, that payment
    is used whatever the model returned; with more than one unpaid
    payment, the result asks which one, listing the payments by month.
    With lang set to Portuguese, the questions are fully Portuguese;
    otherwise they are English. This function never raises for a move
    it was given: refusals from the engine become questions.
    """
    pt = (lang == "pt")

    def ask(text_en, text_pt):
        return {"status": "question",
                "question": text_pt if pt else text_en}

    if not isinstance(sentence, str) or not sentence.strip():
        return ask("Which payment should I move, and to which month?",
                   "Que pagamento devo mover, e para que mês?")
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
    if not isinstance(deal, str) or not deal:
        return ask("Which payment should I move?",
                   "Que pagamento devo mover?")
    if payment is not None and not isinstance(payment, str):
        return ask("Which payment should I move?",
                   "Que pagamento devo mover?")
    if isinstance(target, str) and not MONTH_RE.fullmatch(target):
        resolved = resolve_month_reference(target, current_month)
        target = resolved if resolved is not None else target
    if not isinstance(target, str) or not MONTH_RE.fullmatch(target):
        return ask(
            "Which month should the %s %s payment move to?"
            % (deal, payment),
            "Para que mês deve o pagamento %s %s ser movido?"
            % (deal, payment or ""),
        )
    if isinstance(records, (list, tuple)):
        resolved = _resolve_deal(deal, records)
        if len(resolved) == 1:
            deal = resolved[0]["deal"]
        elif len(resolved) > 1:
            exact = {entry["deal"] for entry in resolved}
            if len(exact) == 1:
                deal = resolved[0]["deal"]
            else:
                names = ", ".join(
                    "%s (%s)" % (entry["deal"], entry["month"])
                    for entry in resolved)
                return ask(
                    "Which %s payment did you mean: %s?" % (deal, names),
                    "Qual pagamento %s: %s?" % (deal, names))
        elif records:
            names = ", ".join(
                "%s (%s)" % (entry["deal"], entry.get("month", ""))
                for entry in records)
            return ask(
                "%s was not found. Registered deals: %s. "
                "Which payment should I move?" % (deal, names),
                "%s não foi encontrado. Negócios registados: %s. "
                "Que pagamento devo mover?" % (deal, names),
            )
    deal_records = []
    if isinstance(records, (list, tuple)):
        deal_records = [
            entry for entry in records
            if normalize_name(entry.get("deal", ""))
            == normalize_name(deal)
        ]
    unpaid = [entry for entry in deal_records
              if not entry.get("received", False)]
    if len(unpaid) == 1:
        payment = unpaid[0].get("payment", "")
    elif len(unpaid) > 1:
        matches = [entry for entry in unpaid
                   if entry.get("payment", "") == payment]
        if len(matches) == 1 and isinstance(payment, str) and payment:
            payment = matches[0].get("payment", "")
        else:
            names = ", ".join(
                "%s (%s)" % (entry.get("payment", ""),
                             entry.get("month", ""))
                for entry in unpaid)
            return ask(
                "Which %s payment should I move: %s?" % (deal, names),
                "Qual pagamento %s deve ser movido: %s?" % (deal, names),
            )
    if not isinstance(payment, str) or not payment:
        if not deal_records:
            pass
        else:
            return ask("Which %s payment should I move?" % deal,
                       "Que pagamento %s deve ser movido?" % deal)
    try:
        outcome = move_payment(
            records,
            {"deal": deal, "payment": payment, "target_month": target},
            current_month,
            expenses_cents=expenses_cents,
        )
    except ValueError:
        return ask("That move is not possible. "
                   "Which payment should I move?",
                   "Esse movimento não é possível. "
                   "Que pagamento devo mover?")
    return {
        "status": "moved",
        "moved": outcome["moved"],
        "before": _forecast(records, expenses_cents),
        "after": outcome["forecast"],
    }
