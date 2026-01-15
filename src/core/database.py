"""Модуль с моделями базы данных SQLAlchemy для PostgreSQL."""

import re
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    String,
    create_engine,
    event,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.orm.session import Session

from .models import Category, Confidence, Currency

Base = declarative_base()


def _normalize_string_for_db(value: str | None) -> str | None:
    """
    Нормализует строку для безопасной записи в БД.
    Удаляет недопустимые последовательности байт и приводит к UTF-8.
    """
    if value is None:
        return None
    
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:
            return None
    
    try:
        # Если это bytes, пробуем декодировать
        if isinstance(value, bytes):
            try:
                value = value.decode('utf-8', errors='strict')
            except UnicodeDecodeError:
                try:
                    value = value.decode('windows-1251', errors='replace')
                except Exception:
                    value = value.decode('utf-8', errors='replace')
        
        # Удаляем проблемные последовательности байт
        value = value.replace('\xc2\xc0', '').replace('\x00', '').replace('\ufffd', '')
        
        # Перекодируем для очистки
        try:
            value_bytes = value.encode('utf-8', errors='replace')
            value = value_bytes.decode('utf-8', errors='replace')
        except Exception:
            pass
        
        # Удаляем непечатаемые символы
        value = re.sub(r'[^\x20-\x7E\n\r\t\u00A0-\uFFFF]', '', value)
        
        return value.strip() if value else None
    except Exception:
        return None


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


# Event listeners для нормализации строк перед записью в БД
# Должны быть определены ПОСЛЕ определения всех классов моделей
@event.listens_for(BankProductDB, 'before_insert', propagate=True)
@event.listens_for(BankProductDB, 'before_update', propagate=True)
def normalize_bank_product_strings(mapper, connection, target):
    """Нормализует все строковые поля перед записью в БД."""
    if hasattr(target, 'bank'):
        target.bank = _normalize_string_for_db(target.bank) or ""
    if hasattr(target, 'bank_logo'):
        target.bank_logo = _normalize_string_for_db(target.bank_logo)
    if hasattr(target, 'product'):
        target.product = _normalize_string_for_db(target.product) or ""
    if hasattr(target, 'term'):
        target.term = _normalize_string_for_db(target.term)
    if hasattr(target, 'grace_period'):
        target.grace_period = _normalize_string_for_db(target.grace_period)
    if hasattr(target, 'cashback'):
        target.cashback = _normalize_string_for_db(target.cashback)
    if hasattr(target, 'commission'):
        target.commission = _normalize_string_for_db(target.commission)
    if hasattr(target, 'unique_key'):
        target.unique_key = _normalize_string_for_db(target.unique_key) or ""


@event.listens_for(CurrencyRateDB, 'before_insert', propagate=True)
@event.listens_for(CurrencyRateDB, 'before_update', propagate=True)
def normalize_currency_rate_strings(mapper, connection, target):
    """Нормализует все строковые поля перед записью в БД."""
    if hasattr(target, 'code'):
        target.code = _normalize_string_for_db(target.code) or ""
    if hasattr(target, 'name'):
        target.name = _normalize_string_for_db(target.name) or ""


class DatabaseManager:
    """Менеджер для работы с базой данных."""

    def __init__(self, database_url: str):
        """
        Инициализация менеджера БД.

        Args:
            database_url: URL подключения к БД (например: postgresql://user:pass@localhost/dbname)
        """
        # Добавляем параметры кодировки для PostgreSQL
        # Если URL уже содержит параметры, добавляем к ним, иначе добавляем новые
        if '?' in database_url:
            database_url_with_encoding = f"{database_url}&client_encoding=utf8"
        else:
            database_url_with_encoding = f"{database_url}?client_encoding=utf8"
        
        self.engine = create_engine(
            database_url_with_encoding,
            pool_pre_ping=True,  # Проверка соединения перед использованием
            pool_recycle=3600,  # Переподключение каждые 3600 секунд
            echo=False,  # Отключить SQL логирование (можно включить для отладки)
            connect_args={
                "options": "-c client_encoding=UTF8"  # Устанавливаем кодировку для подключения
            },
            # Используем psycopg2 напрямую с правильными настройками
            poolclass=None,  # Используем QueuePool по умолчанию
        )
        
        # Устанавливаем кодировку для всех новых соединений
        @event.listens_for(self.engine, "connect")
        def set_encoding(dbapi_conn, connection_record):
            """Устанавливает кодировку UTF-8 для каждого соединения."""
            try:
                with dbapi_conn.cursor() as cursor:
                    cursor.execute("SET client_encoding TO 'UTF8'")
            except Exception as e:
                print(f"Ошибка установки кодировки: {e}")
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
