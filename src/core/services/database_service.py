"""Сервис для работы с базой данных."""

import asyncio
from datetime import datetime, timedelta
from typing import List
from uuid import uuid4

from sqlalchemy import and_

from ..database import BankProductDB, DatabaseManager
from ..models import BankProduct


class DatabaseService:
    """Сервис для работы с базой данных."""

    def __init__(self, db_manager: DatabaseManager):
        """
        Инициализация сервиса БД.

        Args:
            db_manager: Менеджер базы данных
        """
        self.db_manager = db_manager
        # Создаем таблицы при инициализации
        self.db_manager.create_tables()

    def _bank_product_to_db(self, product: BankProduct) -> BankProductDB:
        """Конвертирует BankProduct в BankProductDB."""
        return BankProductDB(
            id=product.id,
            bank=product.bank,
            bank_logo=product.bank_logo,
            product=product.product,
            category=product.category,
            rate_min=product.rate_min,
            rate_max=product.rate_max,
            amount_min=product.amount_min,
            amount_max=product.amount_max,
            term=product.term,
            currency=product.currency,
            confidence=product.confidence,
            grace_period=product.grace_period,
            cashback=product.cashback,
            commission=product.commission,
            collected_at=product.collected_at,
            unique_key=BankProductDB.create_unique_key(
                product.bank, product.product, product.category
            ),
            is_active=True,
        )

    def _db_to_bank_product(self, db_product: BankProductDB) -> BankProduct:
        """Конвертирует BankProductDB в BankProduct."""
        return BankProduct(
            id=db_product.id,
            bank=db_product.bank,
            bank_logo=db_product.bank_logo,
            product=db_product.product,
            category=db_product.category,
            rate_min=db_product.rate_min,
            rate_max=db_product.rate_max,
            amount_min=db_product.amount_min,
            amount_max=db_product.amount_max,
            term=db_product.term,
            currency=db_product.currency,
            confidence=db_product.confidence,
            collected_at=db_product.collected_at,
            grace_period=db_product.grace_period,
            cashback=db_product.cashback,
            commission=db_product.commission,
        )

    async def load_all_products(self) -> List[BankProduct]:
        """
        Загружает все активные продукты из БД.

        Returns:
            Список всех активных продуктов
        """

        def _load():
            session = self.db_manager.get_session()
            try:
                db_products = (
                    session.query(BankProductDB)
                    .filter(BankProductDB.is_active == True)
                    .order_by(BankProductDB.collected_at.desc())
                    .all()
                )
                return [self._db_to_bank_product(p) for p in db_products]
            finally:
                session.close()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _load)

    async def save_products(self, products: List[BankProduct]) -> int:
        """
        Сохраняет или обновляет продукты в БД.

        Args:
            products: Список продуктов для сохранения

        Returns:
            Количество сохраненных/обновленных продуктов
        """

        def _save():
            session = self.db_manager.get_session()
            try:
                saved_count = 0

                for product in products:
                    # Проверяем, существует ли продукт с таким unique_key
                    unique_key = BankProductDB.create_unique_key(
                        product.bank, product.product, product.category
                    )

                    existing = (
                        session.query(BankProductDB)
                        .filter(BankProductDB.unique_key == unique_key)
                        .first()
                    )

                    if existing:
                        # Обновляем существующую запись
                        existing.bank = product.bank
                        existing.bank_logo = product.bank_logo
                        existing.product = product.product
                        existing.category = product.category
                        existing.rate_min = product.rate_min
                        existing.rate_max = product.rate_max
                        existing.amount_min = product.amount_min
                        existing.amount_max = product.amount_max
                        existing.term = product.term
                        existing.currency = product.currency
                        existing.confidence = product.confidence
                        existing.grace_period = product.grace_period
                        existing.cashback = product.cashback
                        existing.commission = product.commission
                        existing.collected_at = product.collected_at
                        existing.updated_at = datetime.now()
                        existing.is_active = True
                    else:
                        # Создаем новую запись
                        if not product.id:
                            product.id = str(uuid4())

                        db_product = self._bank_product_to_db(product)
                        session.add(db_product)

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

    async def mark_products_inactive(self, keep_unique_keys: List[str]) -> int:
        """
        Помечает продукты как неактивные, которых нет в списке актуальных.

        Args:
            keep_unique_keys: Список unique_key продуктов, которые нужно оставить активными

        Returns:
            Количество помеченных как неактивные продуктов
        """

        def _mark_inactive():
            session = self.db_manager.get_session()
            try:
                # Если список актуальных пуст, помечаем все как неактивные
                if not keep_unique_keys:
                    updated = (
                        session.query(BankProductDB)
                        .filter(BankProductDB.is_active == True)
                        .update({"is_active": False, "updated_at": datetime.now()})
                    )
                else:
                    # Помечаем как неактивные все продукты, которых нет в списке актуальных
                    updated = (
                        session.query(BankProductDB)
                        .filter(
                            and_(
                                BankProductDB.is_active == True,
                                ~BankProductDB.unique_key.in_(keep_unique_keys),
                            )
                        )
                        .update({"is_active": False, "updated_at": datetime.now()})
                    )
                session.commit()
                return updated
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _mark_inactive)

    async def delete_inactive_products(self, older_than_days: int = 7) -> int:
        """
        Удаляет неактивные продукты старше указанного количества дней.

        Args:
            older_than_days: Удалять продукты, неактивные более N дней

        Returns:
            Количество удаленных продуктов
        """

        def _delete():
            session = self.db_manager.get_session()
            try:
                cutoff_date = datetime.now() - timedelta(days=older_than_days)

                deleted = (
                    session.query(BankProductDB)
                    .filter(
                        and_(
                            BankProductDB.is_active == False,
                            BankProductDB.updated_at < cutoff_date,
                        )
                    )
                    .delete()
                )
                session.commit()
                return deleted
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _delete)

    async def update_products_from_parsing(
        self, new_products: List[BankProduct]
    ) -> tuple[int, int]:
        """
        Обновляет продукты в БД на основе новых данных парсинга.
        Помечает неактуальные записи как неактивные.

        Args:
            new_products: Список новых продуктов из парсинга

        Returns:
            Кортеж (количество сохраненных/обновленных, количество помеченных как неактивные)
        """
        # Сохраняем новые продукты
        saved_count = await self.save_products(new_products)

        # Определяем список актуальных unique_key
        keep_unique_keys = [
            BankProductDB.create_unique_key(p.bank, p.product, p.category)
            for p in new_products
        ]

        # Помечаем неактуальные как неактивные
        marked_inactive = await self.mark_products_inactive(keep_unique_keys)

        return saved_count, marked_inactive
