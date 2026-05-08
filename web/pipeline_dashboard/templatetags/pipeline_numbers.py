from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from django import template


register = template.Library()


@register.filter
def space_int(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return str(value)
    return f"{int(number):,}".replace(",", " ")
