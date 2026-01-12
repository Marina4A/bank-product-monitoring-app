from typing import List, Optional

from ..models import BankProduct, Filters
from .database_service import DatabaseService
from .parsing_service import ParsingService


class DataService:
    """Сервис для работы с данными."""

    def __init__(
        self,
        database_service: Optional[DatabaseService] = None,
        parsing_service: Optional[ParsingService] = None,
    ):
        """
        Инициализация сервиса данных.

        Args:
            database_service: Сервис работы с БД (опционально)
            parsing_service: Сервис парсинга (опционально)
        """
        self._products: List[BankProduct] = []
        self._database_service = database_service
        self._parsing_service = parsing_service

    def add_products(self, products: List[BankProduct]) -> None:
        """
        Добавляет продукты в список (для постепенного обновления).

        Args:
            products: Список продуктов для добавления
        """
        # Добавляем только новые продукты (по ID или комбинации банк+продукт)
        existing_keys = {(p.bank, p.product) for p in self._products}
        new_products = [
            p for p in products
            if (p.bank, p.product) not in existing_keys
        ]
        self._products.extend(new_products)

    async def load_products(self) -> List[BankProduct]:
        """
        Загружает список банковских продуктов из БД.
        Не запускает парсинг автоматически - только загрузка из БД.
        """
        if self._database_service:
            # Загружаем продукты из БД
            self._products = await self._database_service.load_all_products()
        return self._products

    async def refresh_products(self) -> List[BankProduct]:
        """
        Обновляет список продуктов через парсинг и сохраняет в БД.
        Помечает неактуальные записи как неактивные.
        """
        if not self._parsing_service:
            return self._products

        try:
            # Запускаем парсинг всех банков
            new_products = await self._parsing_service.parse_all_banks()

            # Сохраняем в БД и обновляем статус записей
            if self._database_service and new_products:
                saved_count, marked_inactive = (
                    await self._database_service.update_products_from_parsing(new_products)
                )
                print(
                    f"Обновление БД: сохранено/обновлено {saved_count}, "
                    f"помечено неактивными {marked_inactive}"
                )

                # Загружаем актуальные продукты из БД
                self._products = await self._database_service.load_all_products()
            else:
                # Если БД нет, используем данные из памяти
                self._products = new_products

        except Exception as e:
            print(f"Ошибка обновления продуктов: {e}")
            # В случае ошибки, загружаем продукты из БД, если БД доступна
            if self._database_service:
                try:
                    self._products = await self._database_service.load_all_products()
                except Exception as db_error:
                    print(f"Ошибка загрузки из БД: {db_error}")

        return self._products

    def filter_products(self, products: List[BankProduct], filters: Filters) -> List[BankProduct]:
        """
        Фильтрует продукты по заданным критериям.
        """
        filtered = products

        if filters.bank != "all":
            filtered = [p for p in filtered if p.bank == filters.bank]

        if filters.category != "all":
            filtered = [p for p in filtered if p.category.value == filters.category]

        if filters.currency != "all":
            filtered = [p for p in filtered if p.currency.value == filters.currency]

        if filters.search_query:
            query = filters.search_query.lower()
            filtered = [
                p for p in filtered
                if query in p.bank.lower() or query in p.product.lower()
            ]

        # Фильтрация по диапазону ставок
        # Если ставка = 0, пропускаем продукт через фильтр (не фильтруем по ставке)
        filtered = [
            p for p in filtered
            if p.rate_max == 0.0 or (filters.rate_range[0] <= p.rate_max <= filters.rate_range[1])
        ]

        # Фильтрация по диапазону сумм
        # Если сумма = 0, пропускаем продукт через фильтр (не фильтруем по сумме)
        # Расширяем диапазон сумм, чтобы не фильтровать продукты с большими суммами
        expanded_amount_range = (filters.amount_range[0], max(filters.amount_range[1], 100_000_000_000))
        filtered = [
            p for p in filtered
            if p.amount_max == 0.0 or expanded_amount_range[0] <= p.amount_max <= expanded_amount_range[1]
        ]

        # Фильтрация по датам - ОТКЛЮЧЕНА по умолчанию
        # Фильтр по датам применяется только если пользователь явно установил даты в UI

        return filtered

    def sort_products(
        self,
        products: List[BankProduct],
        field: str,
        ascending: bool = True
    ) -> List[BankProduct]:
        """
        Сортирует продукты по указанному полю.
        TODO: Реализовать логику сортировки.
        """
        reverse = not ascending

        if field == "bank":
            return sorted(products, key=lambda p: p.bank, reverse=reverse)
        elif field == "product":
            return sorted(products, key=lambda p: p.product, reverse=reverse)
        elif field == "rateMin":
            return sorted(products, key=lambda p: p.rate_min, reverse=reverse)
        elif field == "rateMax":
            return sorted(products, key=lambda p: p.rate_max, reverse=reverse)
        elif field == "amountMin":
            return sorted(products, key=lambda p: p.amount_min, reverse=reverse)
        elif field == "collectedAt":
            return sorted(products, key=lambda p: p.collected_at, reverse=reverse)

        return products
