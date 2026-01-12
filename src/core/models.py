from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Category(str, Enum):
    """Категории банковских продуктов."""

    DEPOSIT = "deposit"
    CREDIT = "credit"
    DEBIT_CARD = "debitcard"
    CREDIT_CARD = "creditcard"


class Currency(str, Enum):
    """Валюты."""

    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"
    CNY = "CNY"


class Confidence(str, Enum):
    """Уровень уверенности в данных."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class BankProduct:
    """Модель банковского продукта."""

    id: str
    bank: str
    bank_logo: Optional[str] = None
    product: str = ""
    category: Category = Category.DEPOSIT
    rate_min: float = 0.0
    rate_max: float = 0.0
    amount_min: float = 0.0
    amount_max: float = 0.0
    term: str = ""
    currency: Currency = Currency.RUB
    confidence: Confidence = Confidence.MEDIUM
    collected_at: datetime = None
    grace_period: Optional[str] = None
    cashback: Optional[str] = None
    commission: Optional[str] = None

    def __post_init__(self):
        if self.collected_at is None:
            self.collected_at = datetime.now()


@dataclass
class Filters:
    """Фильтры для поиска продуктов."""

    bank: str = "all"
    category: str = "all"  # Category | "all"
    currency: str = "all"  # Currency | "all"
    date_from: datetime = None
    date_to: datetime = None
    search_query: str = ""
    rate_range: tuple[float, float] = (0.0, 20.0)
    amount_range: tuple[float, float] = (0.0, 10000000.0)

    def __post_init__(self):
        if self.date_from is None:
            self.date_from = datetime.now()
        if self.date_to is None:
            self.date_to = datetime.now()


@dataclass
class LogEntry:
    """Запись в логе."""

    id: str
    timestamp: datetime
    level: str  # "INFO" | "WARNING" | "ERROR"
    message: str

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
