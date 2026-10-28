"""Per-part calculation with integer cents and exact decimal rates."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _check_amount(value, name):
    """Require an integer number of cents."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(name + " must be integer cents")
    return value


def _parse_rate(value, name):
    """Parse an exact decimal rate given as a string."""
    if isinstance(value, bool):
        raise TypeError(name + " must be a decimal string, not bool")
    if isinstance(value, float):
        raise TypeError(name + " must be a decimal string, not float")
    if isinstance(value, int):
        rate = Decimal(value)
    elif isinstance(value, str):
        try:
            rate = Decimal(value)
        except InvalidOperation:
            raise ValueError(name + " is not a valid decimal rate")
    else:
        raise TypeError(name + " must be a decimal string")
    if not rate.is_finite():
        raise ValueError(name + " must be a finite decimal rate")
    if rate < 0 or rate > 1:
        raise ValueError(name + " must be between 0 and 1")
    return rate


def _component(base, rate):
    """Round one component half-up to the cent."""
    return int((Decimal(base) * rate).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP))


def _check_other_rates(other_rates):
    if other_rates is None:
        return {}
    if not isinstance(other_rates, dict):
        raise ValueError("other_rates must be a mapping of name to rate")
    parsed = {}
    for name, value in other_rates.items():
        parsed[name] = _parse_rate(value, "other rate " + str(name))
    return parsed


def calc_part(part_base, iva_rate="0", retencao_rate="0", irs_rate="0",
              ss_rate="0", other_rates=None):
    """Calculate every component of one part in integer cents."""
    base = _check_amount(part_base, "part_base")
    if base < 0:
        raise ValueError("part_base must not be negative")
    iva = _parse_rate(iva_rate, "iva_rate")
    retencao = _parse_rate(retencao_rate, "retencao_rate")
    irs = _parse_rate(irs_rate, "irs_rate")
    ss = _parse_rate(ss_rate, "ss_rate")
    others = _check_other_rates(other_rates)

    iva_cents = _component(base, iva)
    retencao_cents = _component(base, retencao)
    irs_target = _component(base, irs)
    irs_reserve = irs_target - retencao_cents
    if irs_reserve < 0:
        irs_reserve = 0
    ss_reserve = _component(base, ss)
    other = {}
    for name, rate in others.items():
        other[name] = _component(base, rate)
    protected_money = (iva_cents + irs_reserve + ss_reserve
                       + sum(other.values()))
    return {
        "iva": iva_cents,
        "retencao": retencao_cents,
        "bank_inflow": base + iva_cents - retencao_cents,
        "irs_target": irs_target,
        "irs_reserve": irs_reserve,
        "ss_reserve": ss_reserve,
        "other": other,
        "protected_money": protected_money,
    }


def calc_month(parts, expenses=0):
    """Aggregate one month from already-rounded part components.

    Each part is calculated independently and the cent components are
    summed without re-rounding. Really available is bank inflow minus
    protected money minus expenses and may be negative.
    """
    expense_cents = _check_amount(expenses, "expenses")
    if expense_cents < 0:
        raise ValueError("expenses must not be negative")
    if not isinstance(parts, (list, tuple)):
        raise ValueError("parts must be a list of part dicts")
    if len(parts) == 0:
        raise ValueError("parts must not be empty")

    commission = 0
    bank_inflow = 0
    iva_total = 0
    irs_reserve_total = 0
    ss_reserve_total = 0
    other_totals = {}
    for part in parts:
        if not isinstance(part, dict):
            raise ValueError("each part must be a dict")
        if "part_base" not in part:
            raise ValueError("each part must include part_base")
        part_base = part["part_base"]
        result = calc_part(
            part_base,
            part.get("iva_rate", "0"),
            part.get("retencao_rate", "0"),
            part.get("irs_rate", "0"),
            part.get("ss_rate", "0"),
            part.get("other_rates"),
        )
        # calc_part already validated part_base as integer cents.
        commission += part_base
        bank_inflow += result["bank_inflow"]
        iva_total += result["iva"]
        irs_reserve_total += result["irs_reserve"]
        ss_reserve_total += result["ss_reserve"]
        for name, value in result["other"].items():
            other_totals[name] = other_totals.get(name, 0) + value
    protected_money = (iva_total + irs_reserve_total + ss_reserve_total
                       + sum(other_totals.values()))
    return {
        "commission": commission,
        "bank_inflow": bank_inflow,
        "protected_money": protected_money,
        "protected_breakdown": {
            "iva": iva_total,
            "irs_reserve": irs_reserve_total,
            "ss_reserve": ss_reserve_total,
            "other": other_totals,
        },
        "really_available": bank_inflow - protected_money - expense_cents,
    }
