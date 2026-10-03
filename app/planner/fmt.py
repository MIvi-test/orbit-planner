"""Форматирование чисел и слов для текстов причин."""
from __future__ import annotations

from decimal import Decimal


def _sprints_word(n: int) -> str:
    """«2 спринта», «5 спринтов» — текст причин читает заказчик."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} спринт"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} спринта"
    return f"{n} спринтов"


def _q(value: Decimal) -> str:
    """Два знака без хвостовых нулей: 40.00 -> 40, 7.20 -> 7.2."""
    text = f"{value.quantize(Decimal('0.01'))}"
    return text.rstrip("0").rstrip(".") if "." in text else text
