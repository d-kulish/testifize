from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime
from typing import Any

from django import template
from django.utils import timezone


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




MONTHS = {
    "january": "Jan", "february": "Feb", "march": "Mar", "april": "Apr",
    "may": "May", "june": "Jun", "july": "Jul", "august": "Aug",
    "september": "Sep", "october": "Oct", "november": "Nov", "december": "Dec",
}


@register.filter
def sum_attribute(items: Any, attr: str) -> Any:
    if not items:
        return 0
    total = 0
    for item in items:
        value = getattr(item, attr, 0) or 0
        try:
            total += float(value)
        except (TypeError, ValueError):
            pass
    return total


@register.filter
def short_period(value: Any) -> str:
    if not value:
        return "-"
    text = str(value).strip()
    # Accept formats like "April_2026", "April 2026", "April-2026", "2026_04"
    # Try month-year order first
    parts = text.replace("-", "_").replace(" ", "_").split("_")
    if len(parts) == 2:
        first, second = parts
        month_abbr = MONTHS.get(first.lower())
        if month_abbr:
            year = second[-2:] if len(second) >= 2 else second
            return f"{month_abbr} {year}"
        # Try year-month (e.g. 2026_04)
        month_abbr = MONTHS.get(second.lower())
        if month_abbr:
            year = first[-2:] if len(first) >= 2 else first
            return f"{month_abbr} {year}"
    # Single word month only
    month_abbr = MONTHS.get(text.lower())
    if month_abbr:
        return month_abbr
    return text


@register.filter
def days_since(value: Any) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(str(value).strip())
        # Ensure timezone-aware comparison
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        delta = timezone.now() - dt
        days = delta.days
        if days < 0:
            return "0d"
        if days == 0:
            return "Today"
        return f"{days}d"
    except (ValueError, TypeError):
        return "-"
