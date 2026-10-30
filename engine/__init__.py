"""Deterministic calculation engine.

Money is integer cents everywhere and rates are exact decimals given as
strings. Rounding is half-up to the cent, applied to each component
independently. The functions are pure: no I/O, no clock, no global state.
"""

from engine.calc import agent_share, calc_month, calc_part
from engine.move import move_payment

ENGINE_VERSION = 1

__all__ = ["ENGINE_VERSION", "agent_share", "calc_month", "calc_part",
           "move_payment"]
