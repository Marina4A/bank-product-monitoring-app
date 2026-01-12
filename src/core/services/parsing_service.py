import asyncio
import uuid
from datetime import datetime
from typing import Any, Callable, List, Optional

from core.models import BankProduct, Category, Confidence, Currency
from core.normalizers.gigachat import (
    CREDIT_CARD_SCHEMA,
    CREDIT_PRODUCT_SCHEMA,
    DEBIT_CARD_SCHEMA,
    GigaChatNormalizer,
)
from core.parsers.alpha_credit_card import AlphaCreditCardParser
from core.parsers.alpha_credit_products import AlphaCreditProductsParser
from core.parsers.alpha_debit_card import AlphaDebitCardParser
from core.parsers.gazprombank_credit_card import GazprombankCreditCardParser
from core.parsers.gazprombank_credit_products import GazprombankCreditProductsParser
from core.parsers.gazprombank_debit_card import GazprombankDebitCardParser
from core.parsers.sberbank_credit_card import SberbankCreditCardSeleniumParser
from core.parsers.sberbank_credit_products import SberbankCreditProductsSeleniumParser
from core.parsers.sberbank_debit_card import SberbankDebitCardSeleniumParser
from core.parsers.tinkoff_credit_card import TinkoffCreditCardParser
from core.parsers.tinkoff_credit_products import TinkoffCreditProductsParser
from core.parsers.tinkoff_debit_card import TinkoffDebitCardParser
from core.parsers.vtb_credit_card import VTBCreditCardParser
from core.parsers.vtb_credit_products import VTBCreditProductsParser
from core.parsers.vtb_debit_card import VTBDebitCardParser


class ParsingService:
    """Сервис для парсинга банковских продуктов."""

    def __init__(
        self,
        timeout: float = 30.0,
        retries: int = 3,
        headless: bool = True,
        on_product_parsed: Optional[Callable[[List[BankProduct]], None]] = None,
    ):
        """
        Инициализация сервиса парсинга.

        Args:
            timeout: Таймаут для запросов в секундах
            retries: Количество повторов при ошибках
            headless: Запуск браузера в headless режиме
            on_product_parsed: Callback функция, вызываемая после парсинга каждого банка
        """
        self.timeout = timeout
        self.retries = retries
        self.headless = headless
        self._normalizer: Optional[GigaChatNormalizer] = None
        # Lock для последовательной нормализации через GigaChat
        self._normalization_lock = asyncio.Lock()
        # Callback для обновления UI после парсинга
        self.on_product_parsed = on_product_parsed

    async def _get_normalizer(self) -> Optional[GigaChatNormalizer]:
        """Получает нормализатор (создает при первом обращении)."""
        if self._normalizer is None:
            try:
                self._normalizer = GigaChatNormalizer()
            except Exception:
                # Если не удалось инициализировать нормализатор, продолжаем без него
                return None
        return self._normalizer

    async def parse_all_banks(self) -> List[BankProduct]:
        """
        Парсит данные со всех банков.

        Returns:
            Список банковских продуктов
        """
        all_products: List[BankProduct] = []

        # Список задач для параллельного выполнения
        # Запускаем парсеры последовательно, чтобы не перегружать систему
        # Можно запускать параллельно, но с ограничением количества одновременных задач
        parsers = [
            ("Альфа-Банк: кредитные продукты", self._parse_alpha_credit_products),
            ("Альфа-Банк: дебетовые карты", self._parse_alpha_debit_cards),
            ("Альфа-Банк: кредитные карты", self._parse_alpha_credit_cards),
            ("ТБанк: кредитные продукты", self._parse_tinkoff_credit_products),
            ("ТБанк: дебетовые карты", self._parse_tinkoff_debit_cards),
            ("ТБанк: кредитные карты", self._parse_tinkoff_credit_cards),
            ("ВТБ: кредитные продукты", self._parse_vtb_credit_products),
            ("ВТБ: дебетовые карты", self._parse_vtb_debit_cards),
            ("ВТБ: кредитные карты", self._parse_vtb_credit_cards),
            ("Газпромбанк: кредитные продукты", self._parse_gazprom_credit_products),
            ("Газпромбанк: дебетовые карты", self._parse_gazprom_debit_cards),
            ("Газпромбанк: кредитные карты", self._parse_gazprom_credit_cards),
            ("Сбербанк: кредитные продукты", self._parse_sberbank_credit_products),
            ("Сбербанк: дебетовые карты", self._parse_sberbank_debit_cards),
            ("Сбербанк: кредитные карты", self._parse_sberbank_credit_cards),
        ]

        # Запускаем парсеры с задержкой между ними, чтобы не перегружать систему
        for name, parser_func in parsers:
            try:
                print(f"Парсинг: {name}...")
                products = await parser_func()
                all_products.extend(products)
                print(f"Парсинг {name} завершен. Найдено продуктов: {len(products)}")

                # Вызываем callback для обновления UI после каждого успешного парсинга
                if products and self.on_product_parsed:
                    try:
                        # Вызываем async callback
                        await self.on_product_parsed(products)
                    except Exception as e:
                        print(f"Ошибка в callback on_product_parsed: {e}")
                        import traceback
                        traceback.print_exc()

                # Небольшая задержка между парсерами
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Ошибка парсинга {name}: {e}")
                continue

        return all_products

    async def _normalize_items(
        self,
        items: List[Any],
        schema: dict[str, Any],
        description: str,
    ) -> List[dict[str, Any]]:
        """
        Нормализует элементы последовательно через GigaChat.

        Args:
            items: Список элементов для нормализации
            schema: JSON схема
            description: Описание контекста

        Returns:
            Список нормализованных элементов
        """
        normalizer = await self._get_normalizer()
        if not normalizer:
            return items

        # Используем lock для гарантии последовательной нормализации
        async with self._normalization_lock:
            return await normalizer.normalize_batch(items, schema, description)

    async def _parse_alpha_credit_products(self) -> List[BankProduct]:
        """Парсит кредитные продукты Альфа-Банка."""
        try:
            async with AlphaCreditProductsParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page("https://alfabank.ru/get-money/")

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("products", []),
                schema=CREDIT_PRODUCT_SCHEMA,
                description="Нормализация данных кредитных продуктов Альфа-Банка.",
            )
            data["products"] = normalized

            return self._convert_credit_products_to_bank_products(
                data.get("products", []), "Альфа-Банк"
            )
        except Exception as e:
            print(f"Ошибка парсинга кредитных продуктов Альфа-Банка: {e}")
            return []

    async def _parse_alpha_debit_cards(self) -> List[BankProduct]:
        """Парсит дебетовые карты Альфа-Банка."""
        try:
            async with AlphaDebitCardParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page("https://alfabank.ru/everyday/debit-cards/")

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("cards", []),
                schema=DEBIT_CARD_SCHEMA,
                description="Нормализация данных дебетовых карт Альфа-Банка.",
            )
            data["cards"] = normalized

            return self._convert_cards_to_bank_products(
                data.get("cards", []), "Альфа-Банк", Category.DEBIT_CARD
            )
        except Exception as e:
            print(f"Ошибка парсинга дебетовых карт Альфа-Банка: {e}")
            return []

    async def _parse_alpha_credit_cards(self) -> List[BankProduct]:
        """Парсит кредитные карты Альфа-Банка."""
        try:
            async with AlphaCreditCardParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page("https://alfabank.ru/get-money/credit-cards/")

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("cards", []),
                schema=CREDIT_CARD_SCHEMA,
                description="Нормализация данных кредитных карт Альфа-Банка.",
            )
            data["cards"] = normalized

            return self._convert_cards_to_bank_products(
                data.get("cards", []), "Альфа-Банк", Category.CREDIT_CARD
            )
        except Exception as e:
            print(f"Ошибка парсинга кредитных карт Альфа-Банка: {e}")
            return []

    async def _parse_tinkoff_credit_products(self) -> List[BankProduct]:
        """Парсит кредитные продукты Тинькофф Банка."""
        try:
            async with TinkoffCreditProductsParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page("https://www.tbank.ru/loans/")

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("products", []),
                schema=CREDIT_PRODUCT_SCHEMA,
                description="Нормализация данных кредитных продуктов Тинькофф Банка.",
            )
            data["products"] = normalized

            return self._convert_credit_products_to_bank_products(
                data.get("products", []), "ТБанк"
            )
        except Exception as e:
            print(f"Ошибка парсинга кредитных продуктов ТБанк: {e}")
            return []

    async def _parse_tinkoff_debit_cards(self) -> List[BankProduct]:
        """Парсит дебетовые карты Тинькофф Банка."""
        try:
            async with TinkoffDebitCardParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page("https://www.tbank.ru/cards/debit-cards/")

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("cards", []),
                schema=DEBIT_CARD_SCHEMA,
                description="Нормализация данных дебетовых карт Тинькофф Банка.",
            )
            data["cards"] = normalized

            return self._convert_cards_to_bank_products(
                data.get("cards", []), "ТБанк", Category.DEBIT_CARD
            )
        except Exception as e:
            print(f"Ошибка парсинга дебетовых карт ТБанк: {e}")
            return []

    async def _parse_tinkoff_credit_cards(self) -> List[BankProduct]:
        """Парсит кредитные карты Тинькофф Банка."""
        try:
            async with TinkoffCreditCardParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page("https://www.tbank.ru/cards/credit-cards/")

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("cards", []),
                schema=CREDIT_CARD_SCHEMA,
                description="Нормализация данных кредитных карт Тинькофф Банка.",
            )
            data["cards"] = normalized

            return self._convert_cards_to_bank_products(
                data.get("cards", []), "ТБанк", Category.CREDIT_CARD
            )
        except Exception as e:
            print(f"Ошибка парсинга кредитных карт ТБанк: {e}")
            return []

    async def _parse_vtb_credit_products(self) -> List[BankProduct]:
        """Парсит кредитные продукты ВТБ."""
        try:
            async with VTBCreditProductsParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page(
                    "https://www.vtb.ru/malyj-biznes/kredity-i-garantii/"
                )

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("products", []),
                schema=CREDIT_PRODUCT_SCHEMA,
                description="Нормализация данных кредитных продуктов ВТБ.",
            )
            data["products"] = normalized

            return self._convert_credit_products_to_bank_products(
                data.get("products", []), "ВТБ"
            )
        except Exception as e:
            print(f"Ошибка парсинга кредитных продуктов ВТБ: {e}")
            return []

    async def _parse_vtb_debit_cards(self) -> List[BankProduct]:
        """Парсит дебетовые карты ВТБ."""
        try:
            async with VTBDebitCardParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page("https://www.vtb.ru/personal/karty/debetovye/")

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("cards", []),
                schema=DEBIT_CARD_SCHEMA,
                description="Нормализация данных дебетовых карт ВТБ.",
            )
            data["cards"] = normalized

            return self._convert_cards_to_bank_products(
                data.get("cards", []), "ВТБ", Category.DEBIT_CARD
            )
        except Exception as e:
            print(f"Ошибка парсинга дебетовых карт ВТБ: {e}")
            return []

    async def _parse_vtb_credit_cards(self) -> List[BankProduct]:
        """Парсит кредитные карты ВТБ."""
        try:
            async with VTBCreditCardParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page("https://www.vtb.ru/personal/karty/kreditnye/")

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("cards", []),
                schema=CREDIT_CARD_SCHEMA,
                description="Нормализация данных кредитных карт ВТБ.",
            )
            data["cards"] = normalized

            return self._convert_cards_to_bank_products(
                data.get("cards", []), "ВТБ", Category.CREDIT_CARD
            )
        except Exception as e:
            print(f"Ошибка парсинга кредитных карт ВТБ: {e}")
            return []

    async def _parse_gazprom_credit_products(self) -> List[BankProduct]:
        """Парсит кредитные продукты Газпромбанка."""
        try:
            async with GazprombankCreditProductsParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page(
                    "https://www.gazprombank.ru/personal/take_credit/consumer_credit/"
                )

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("products", []),
                schema=CREDIT_PRODUCT_SCHEMA,
                description="Нормализация данных кредитных продуктов Газпромбанка.",
            )
            data["products"] = normalized

            return self._convert_credit_products_to_bank_products(
                data.get("products", []), "Газпромбанк"
            )
        except Exception as e:
            print(f"Ошибка парсинга кредитных продуктов Газпромбанка: {e}")
            return []

    async def _parse_gazprom_debit_cards(self) -> List[BankProduct]:
        """Парсит дебетовые карты Газпромбанка."""
        try:
            async with GazprombankDebitCardParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page(
                    "https://www.gazprombank.ru/personal/cards/"
                )

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("cards", []),
                schema=DEBIT_CARD_SCHEMA,
                description="Нормализация данных дебетовых карт Газпромбанка.",
            )
            data["cards"] = normalized

            return self._convert_cards_to_bank_products(
                data.get("cards", []), "Газпромбанк", Category.DEBIT_CARD
            )
        except Exception as e:
            print(f"Ошибка парсинга дебетовых карт Газпромбанка: {e}")
            return []

    async def _parse_gazprom_credit_cards(self) -> List[BankProduct]:
        """Парсит кредитные карты Газпромбанка."""
        try:
            async with GazprombankCreditCardParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page(
                    "https://www.gazprombank.ru/personal/credit-cards/"
                )

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("cards", []),
                schema=CREDIT_CARD_SCHEMA,
                description="Нормализация данных кредитных карт Газпромбанка.",
            )
            data["cards"] = normalized

            return self._convert_cards_to_bank_products(
                data.get("cards", []), "Газпромбанк", Category.CREDIT_CARD
            )
        except Exception as e:
            print(f"Ошибка парсинга кредитных карт Газпромбанка: {e}")
            return []

    async def _parse_sberbank_credit_products(self) -> List[BankProduct]:
        """Парсит кредитные продукты Сбербанка (кредиты и ипотеки)."""
        try:
            async with SberbankCreditProductsSeleniumParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                # Парсим кредиты наличными
                data_credits = await parser.parse_page(
                    "https://www.sberbank.ru/ru/person/credits/money"
                )
                # Парсим ипотеки
                data_home = await parser.parse_page(
                    "https://www.sberbank.ru/ru/person/credits/homenew"
                )

            # Объединяем продукты с обеих страниц
            all_products = data_credits.get("products", []) + data_home.get("products", [])

            if not all_products:
                return []

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=all_products,
                schema=CREDIT_PRODUCT_SCHEMA,
                description="Нормализация данных кредитных продуктов Сбербанка.",
            )

            return self._convert_credit_products_to_bank_products(
                normalized, "Сбербанк"
            )
        except Exception as e:
            print(f"Ошибка парсинга кредитных продуктов Сбербанка: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def _parse_sberbank_debit_cards(self) -> List[BankProduct]:
        """Парсит дебетовые карты Сбербанка."""
        try:
            async with SberbankDebitCardSeleniumParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page(
                    "https://www.sberbank.ru/ru/person/bank_cards/debit"
                )

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("cards", []),
                schema=DEBIT_CARD_SCHEMA,
                description="Нормализация данных дебетовых карт Сбербанка.",
            )
            data["cards"] = normalized

            return self._convert_cards_to_bank_products(
                data.get("cards", []), "Сбербанк", Category.DEBIT_CARD
            )
        except Exception as e:
            print(f"Ошибка парсинга дебетовых карт Сбербанка: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def _parse_sberbank_credit_cards(self) -> List[BankProduct]:
        """Парсит кредитные карты Сбербанка."""
        try:
            async with SberbankCreditCardSeleniumParser(
                headless=self.headless, timeout=self.timeout
            ) as parser:
                data = await parser.parse_page(
                    "https://www.sberbank.ru/ru/person/bank_cards/credit_cards"
                )

            # Нормализация через общий метод с lock
            normalized = await self._normalize_items(
                items=data.get("cards", []),
                schema=CREDIT_CARD_SCHEMA,
                description="Нормализация данных кредитных карт Сбербанка.",
            )
            data["cards"] = normalized

            return self._convert_cards_to_bank_products(
                data.get("cards", []), "Сбербанк", Category.CREDIT_CARD
            )
        except Exception as e:
            print(f"Ошибка парсинга кредитных карт Сбербанка: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _convert_credit_products_to_bank_products(
        self, products: List[dict[str, Any]], bank: str
    ) -> List[BankProduct]:
        """Конвертирует нормализованные кредитные продукты в BankProduct."""
        result = []
        for product in products:
            if "error" in product:
                continue

            # Безопасно получаем значения, обрабатывая None
            price = product.get("price") or ""
            term = product.get("term") or ""

            # Извлекаем ставку из price или term
            rate_min, rate_max = self._extract_rate_from_text(
                f"{price} {term}".strip()
            )

            # Извлекаем сумму из price
            amount_min, amount_max = self._extract_amount_from_text(price)

            # Извлекаем валюту
            currency = self._extract_currency_from_text(price)

            bp = BankProduct(
                id=str(uuid.uuid4()),
                bank=bank,
                product=product.get("title") or "",
                category=Category.CREDIT,
                rate_min=rate_min,
                rate_max=rate_max,
                amount_min=amount_min,
                amount_max=amount_max,
                term=term,
                currency=currency,
                confidence=Confidence.MEDIUM,
                collected_at=datetime.now(),
            )
            result.append(bp)
        return result

    def _convert_cards_to_bank_products(
        self, cards: List[dict[str, Any]], bank: str, category: Category
    ) -> List[BankProduct]:
        """Конвертирует нормализованные карты в BankProduct."""
        result = []
        for card in cards:
            if "error" in card:
                continue

            features = card.get("features", [])
            cashback = None
            grace_period = None
            commission = None
            rate_min = 0.0
            rate_max = 0.0

            # Извлекаем информацию из features
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                label = str(feature.get("label") or "").lower()
                value = str(feature.get("value") or "")
                if "кешбэк" in label or "cashback" in label:
                    cashback = value if value else None
                elif "льготный" in label or "grace" in label or "без процентов" in label:
                    grace_period = value if value else None
                elif "комиссия" in label or "обслуживание" in label:
                    commission = value if value else None
                elif "%" in value or "процент" in label:
                    rate_min, rate_max = self._extract_rate_from_text(value)

            # Извлекаем валюту
            currency = Currency.RUB  # По умолчанию

            bp = BankProduct(
                id=str(uuid.uuid4()),
                bank=bank,
                product=card.get("title") or "",
                category=category,
                rate_min=rate_min,
                rate_max=rate_max,
                amount_min=0.0,
                amount_max=0.0,
                term="",
                currency=currency,
                confidence=Confidence.MEDIUM,
                collected_at=datetime.now(),
                cashback=cashback,
                grace_period=grace_period,
                commission=commission,
            )
            result.append(bp)
        return result

    def _extract_rate_from_text(self, text: str) -> tuple[float, float]:
        """Извлекает ставку из текста."""
        import re

        # Обрабатываем None и пустые строки
        if not text:
            return (0.0, 0.0)

        # Ищем проценты в тексте
        pattern = r"(\d+(?:[.,]\d+)?)\s*%"
        matches = re.findall(pattern, str(text))
        if matches:
            rates = [float(m.replace(",", ".")) for m in matches]
            return (min(rates), max(rates))
        return (0.0, 0.0)

    def _extract_amount_from_text(self, text: str) -> tuple[float, float]:
        """Извлекает сумму из текста."""
        import re

        # Обрабатываем None и пустые строки
        if not text:
            return (0.0, 0.0)

        # Ищем суммы в тексте (млн, тыс, руб)
        pattern = r"(\d+(?:[.,]\d+)?)\s*(млн|тыс|млрд)?"
        matches = re.findall(pattern, str(text))
        if matches:
            amounts = []
            for match in matches:
                value = float(match[0].replace(",", "."))
                multiplier = match[1] if match[1] else ""
                if "млрд" in multiplier:
                    value *= 1_000_000_000
                elif "млн" in multiplier:
                    value *= 1_000_000
                elif "тыс" in multiplier:
                    value *= 1_000
                amounts.append(value)
            if amounts:
                return (min(amounts), max(amounts))
        return (0.0, 0.0)

    def _extract_currency_from_text(self, text: str) -> Currency:
        """Извлекает валюту из текста."""
        if not text:
            return Currency.RUB

        text_upper = str(text).upper()
        if "USD" in text_upper or "$" in text:
            return Currency.USD
        elif "EUR" in text_upper or "€" in text:
            return Currency.EUR
        elif "CNY" in text_upper or "¥" in text or "юань" in str(text).lower():
            return Currency.CNY
        return Currency.RUB
