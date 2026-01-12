"""Модуль с моделями базы данных SQLAlchemy для PostgreSQL."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    String,
    create_engine,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.orm.session import Session

from .models import Category, Confidence, Currency

Base = declarative_base()


class BankProductDB(Base):
    """Модель банковского продукта в базе данных."""

    __tablename__ = "bank_products"

    # Основные поля
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    bank = Column(String, nullable=False, index=True)
    bank_logo = Column(String, nullable=True)
    product = Column(String, nullable=False, index=True)
    category = Column(SQLEnum(Category), nullable=False, index=True)

    # Ставки
    rate_min = Column(Float, nullable=False, default=0.0)
    rate_max = Column(Float, nullable=False, default=0.0)

    # Суммы
    amount_min = Column(Float, nullable=False, default=0.0)
    amount_max = Column(Float, nullable=False, default=0.0)

    # Дополнительные поля
    term = Column(String, nullable=True)
    currency = Column(
        SQLEnum(Currency), nullable=False, default=Currency.RUB, index=True
    )
    confidence = Column(SQLEnum(Confidence), nullable=False, default=Confidence.MEDIUM)

    # Дополнительные характеристики
    grace_period = Column(String, nullable=True)
    cashback = Column(String, nullable=True)
    commission = Column(String, nullable=True)

    # Метаданные
    collected_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    # Флаг актуальности (для отслеживания удаления неактуальных записей)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Уникальный идентификатор для отслеживания обновлений (банк + продукт + категория)
    unique_key = Column(String, nullable=False, index=True)

    def __repr__(self):
        return f"<BankProductDB(id={self.id}, bank={self.bank}, product={self.product})>"

    @classmethod
    def create_unique_key(cls, bank: str, product: str, category: Category) -> str:
        """Создает уникальный ключ для идентификации продукта."""
        return f"{bank}|{product}|{category.value}"


class CurrencyRateDB(Base):
    """Модель курса валюты в базе данных."""

    __tablename__ = "currency_rates"

    # Основные поля
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    code = Column(String, nullable=False, index=True)  # Код валюты (USD, EUR и т.д.)
    name = Column(String, nullable=False)  # Название валюты
    nominal = Column(Float, nullable=False)  # Номинал
    value = Column(Float, nullable=False)  # Курс
    previous = Column(Float, nullable=False)  # Предыдущий курс

    # Дата курса (когда был установлен этот курс)
    rate_date = Column(DateTime, nullable=False, index=True)

    # Метаданные
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    def __repr__(self):
        return f"<CurrencyRateDB(code={self.code}, value={self.value}, date={self.rate_date})>"


class DatabaseManager:
    """Менеджер для работы с базой данных."""

    def __init__(self, database_url: str):
        """
        Инициализация менеджера БД.

        Args:
            database_url: URL подключения к БД (например: postgresql://user:pass@localhost/dbname)
        """
        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,  # Проверка соединения перед использованием
            pool_recycle=3600,  # Переподключение каждые 3600 секунд
            echo=False,  # Отключить SQL логирование (можно включить для отладки)
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )

    def create_tables(self):
        """Создает все таблицы в базе данных."""
        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        """Возвращает новую сессию БД."""
        return self.SessionLocal()

    def close(self):
        """Закрывает соединение с БД."""
        self.engine.dispose()
