"""Move-payment scenario: pure forecast recalculation.

The first Cash-flow Scenario Assistant operation moves one selected
unpaid expected payment to another month and returns the recalculated
forecast. The function is pure: no I/O, no clock, no global state, and
the given records are never changed. Every figure comes from
``engine.calc``; the only work here is selecting the payment,
reassigning its month, and aggregating each month. No model is called
and nothing about how records are saved changes.
"""

import re

from engine.calc import calc_month

MONTH_RE = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")

RATE_KEYS = ("iva_rate", "retencao_rate", "irs_rate", "ss_rate")

ALLOWED_RECORD_KEYS = frozenset((
    "deal",
    "payment",
    "month",
    "part_base",
    "received",
    "iva_rate",
    "retencao_rate",
    "irs_rate",
    "ss_rate",
    "other_rates",
))


def _check_month(value, name):
    if not isinstance(value, str) or not MONTH_RE.fullmatch(value):
        raise ValueError(name + " must be a month like YYYY-MM")
    return value


def _check_records(records):
    if not isinstance(records, (list, tuple)):
        raise ValueError("records must be a list of payment dicts")
    for entry in records:
        if not isinstance(entry, dict):
            raise ValueError("each record must be a dict")
        for key in entry:
            if key not in ALLOWED_RECORD_KEYS:
                raise ValueError("unknown record key: " + str(key))
        for key in ("deal", "payment", "month", "part_base"):
            if key not in entry:
                raise ValueError("each record must include " + key)
        if not isinstance(entry["deal"], str) or not entry["deal"]:
            raise ValueError("record deal must be a non-empty name")
        if not isinstance(entry["payment"], str) or not entry["payment"]:
            raise ValueError("record payment must be a non-empty reference")
        _check_month(entry["month"], "record month")


def _check_move(move):
    if not isinstance(move, dict):
        raise ValueError("move must be a dict")
    for key in ("deal", "payment", "target_month"):
        if key not in move:
            raise ValueError("move must include " + key)
    if not isinstance(move["deal"], str) or not move["deal"]:
        raise ValueError("move deal must be a non-empty name")
    if not isinstance(move["payment"], str) or not move["payment"]:
        raise ValueError("move payment must be a non-empty reference")
    _check_month(move["target_month"], "target month")


def _part_for(entry):
    """Build an engine part dict from a record, leaving it untouched."""
    part = {"part_base": entry["part_base"]}
    for key in RATE_KEYS:
        if key in entry:
            part[key] = entry[key]
    if "other_rates" in entry:
        part["other_rates"] = entry["other_rates"]
    return part


def move_payment(records, move, current_month, expenses_cents=0):
    """Move one unpaid expected payment and return the new forecast.

    ``records`` is a list of payment dicts with ``deal`` (deal name),
    ``payment`` (payment reference within the deal), ``month``
    (``YYYY-MM``), ``part_base`` (integer cents), ``received``
    (true once the payment was received; defaults to false), and the
    engine rate keys (each defaulting to zero). ``move`` names the
    ``deal``, the ``payment`` and the ``target_month``. Months before
    ``current_month`` are past; the current month and later are valid
    targets. The forecast maps each month that still holds unpaid
    expected money to its ``calc_month`` figures; received payments
    are never part of it.

    Refusals, all with ``ValueError``: unknown deal, unknown payment,
    more than one unpaid match for the same deal and payment
    (ambiguous), a payment already received, or a past target month.
    """
    _check_records(records)
    _check_move(move)
    _check_month(current_month, "current month")

    if move["target_month"] < current_month:
        raise ValueError(
            "target month " + move["target_month"] + " is in the past")

    known_deals = [entry for entry in records
                   if entry["deal"] == move["deal"]]
    if not known_deals:
        raise ValueError("unknown deal: " + move["deal"])
    matches = [entry for entry in known_deals
               if entry["payment"] == move["payment"]]
    if not matches:
        raise ValueError("unknown payment: " + move["payment"])
    unpaid = [entry for entry in matches if not entry.get("received", False)]
    if len(unpaid) < len(matches):
        raise ValueError(
            "payment " + move["payment"] + " is already received")
    if len(unpaid) > 1:
        raise ValueError(
            "ambiguous move: more than one unpaid expected payment "
            "matches " + move["deal"] + " " + move["payment"])
    selected = unpaid[0]

    months = {}
    for entry in records:
        if entry.get("received", False):
            continue
        month = entry["month"]
        if entry is selected:
            month = move["target_month"]
        months.setdefault(month, []).append(_part_for(entry))

    return {
        "moved": {
            "deal": move["deal"],
            "payment": move["payment"],
            "from_month": selected["month"],
            "target_month": move["target_month"],
        },
        "forecast": {
            month: calc_month(parts, expenses=expenses_cents)
            for month, parts in sorted(months.items())
        },
    }
