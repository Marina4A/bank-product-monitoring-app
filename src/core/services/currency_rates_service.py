"""Сервис для работы с курсами валют в базе данных."""

import asyncio
from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import and_

from ..database import CurrencyRateDB, DatabaseManager


class CurrencyRatesService:
    """Сервис для работы с курсами валют в БД."""

    def __init__(self, db_manager: DatabaseManager):
        """
        Инициализация сервиса курсов валют.

        Args:
            db_manager: Менеджер базы данных
        """
        self.db_manager = db_manager
        # Создаем таблицы при инициализации
        self.db_manager.create_tables()

    async def save_rates(self, rates_data: List[Dict], rate_date: datetime) -> int:
        """
        Сохраняет курсы валют в БД.

        Args:
            rates_data: Список словарей с данными курсов
                       [{"code": "USD", "name": "Доллар США", "nominal": 1, "value": 75.5, "previous": 75.0}, ...]
            rate_date: Дата установки курсов

        Returns:
            Количество сохраненных курсов
        """

        def _save():
            session = self.db_manager.get_session()
            try:
                # Удаляем старые курсы на эту же дату, если они есть
                # Используем диапазон дат для сравнения (от начала дня до конца дня)
                target_date = (
                    rate_date.date() if isinstance(rate_date, datetime) else rate_date
                )
                start_datetime = datetime.combine(target_date, datetime.min.time())
                end_datetime = datetime.combine(target_date, datetime.max.time())

                session.query(CurrencyRateDB).filter(
                    and_(
                        CurrencyRateDB.rate_date >= start_datetime,
                        CurrencyRateDB.rate_date <= end_datetime,
                    )
                ).delete()

                saved_count = 0
                # Убеждаемся, что rate_date - это datetime объект
                if isinstance(rate_date, date) and not isinstance(rate_date, datetime):
                    rate_date_dt = datetime.combine(rate_date, datetime.min.time())
                else:
                    rate_date_dt = rate_date

                for rate in rates_data:
                    db_rate = CurrencyRateDB(
                        id=str(uuid4()),
                        code=rate.get("code", ""),
                        name=rate.get("name", ""),
                        nominal=rate.get("nominal", 1.0),
                        value=rate.get("value", 0.0),
                        previous=rate.get("previous", 0.0),
                        rate_date=rate_date_dt,
                    )
                    session.add(db_rate)
                    saved_count += 1

                session.commit()
                return saved_count
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _save)

    async def get_rates_by_date(self, target_date: date) -> List[Dict]:
        """
        Получает курсы валют по указанной дате.

        Args:
            target_date: Дата для получения курсов

        Returns:
            Список словарей с данными курсов
        """

        def _get():
            session = self.db_manager.get_session()
            try:
                # Ищем курсы за указанную дату
                start_datetime = datetime.combine(target_date, datetime.min.time())
                end_datetime = datetime.combine(target_date, datetime.max.time())

                db_rates = (
                    session.query(CurrencyRateDB)
                    .filter(
                        and_(
                            CurrencyRateDB.rate_date >= start_datetime,
                            CurrencyRateDB.rate_date <= end_datetime,
                        )
                    )
                    .order_by(CurrencyRateDB.code)
                    .all()
                )

                return [
                    {
                        "code": rate.code,
                        "name": rate.name,
                        "nominal": rate.nominal,
                        "value": rate.value,
                        "previous": rate.previous,
                        "date": rate.rate_date.strftime("%d.%m.%Y"),
                    }
                    for rate in db_rates
                ]
            finally:
                session.close()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get)

    async def has_rates_for_today(self) -> bool:
        """
        Проверяет, есть ли курсы валют на сегодняшний день.

        Returns:
            True, если есть курсы на сегодня, False иначе
        """

        def _check():
            session = self.db_manager.get_session()
            try:
                today = date.today()
                start_datetime = datetime.combine(today, datetime.min.time())
                end_datetime = datetime.combine(today, datetime.max.time())

                count = (
                    session.query(CurrencyRateDB)
                    .filter(
                        and_(
                            CurrencyRateDB.rate_date >= start_datetime,
                            CurrencyRateDB.rate_date <= end_datetime,
                        )
                    )
                    .count()
                )

                return count > 0
            finally:
                session.close()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _check)

    async def get_latest_rates_date(self) -> Optional[date]:
        """
        Получает дату последних сохраненных курсов.

        Returns:
            Дата последних курсов или None, если курсов нет
        """

        def _get():
            session = self.db_manager.get_session()
            try:
                latest_rate = (
                    session.query(CurrencyRateDB)
                    .order_by(CurrencyRateDB.rate_date.desc())
                    .first()
                )

                if latest_rate:
                    return latest_rate.rate_date.date()
                return None
            finally:
                session.close()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get)
