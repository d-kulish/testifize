from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime
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


@register.filter
def short_dt(value: Any) -> str:
    if not value:
        return "-"
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return text


@register.filter
def type_label(extension: Any) -> str:
    if not extension:
        return "Other"
    ext = str(extension).lower()
    if ext in {".xlsx", ".xlsm", ".xls"}:
        return "EXC"
    if ext == ".csv":
        return "CSV"
    if ext in {".txt", ".md", ".log", ".json", ".xml"}:
        return "TXT"
    return "Other"
