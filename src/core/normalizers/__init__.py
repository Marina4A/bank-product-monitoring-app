"""
Модуль нормализаторов данных с использованием различных AI сервисов.
"""

from core.normalizers.gigachat import (
    CREDIT_CARD_SCHEMA,
    CREDIT_PRODUCT_SCHEMA,
    DEBIT_CARD_SCHEMA,
    GigaChatNormalizer,
)

__all__ = [
    "GigaChatNormalizer",
    "CREDIT_PRODUCT_SCHEMA",
    "DEBIT_CARD_SCHEMA",
    "CREDIT_CARD_SCHEMA",
]
