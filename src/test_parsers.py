import asyncio
import sys

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
from core.parsers.moex_securities import MoexSecuritiesParser
from core.parsers.sberbank_credit_card import SberbankCreditCardSeleniumParser
from core.parsers.sberbank_credit_products import SberbankCreditProductsSeleniumParser
from core.parsers.sberbank_debit_card import SberbankDebitCardSeleniumParser
from core.parsers.banki_ratings import BankiRatingsParser
from core.parsers.tinkoff_credit_card import TinkoffCreditCardParser
from core.parsers.tinkoff_credit_products import TinkoffCreditProductsParser
from core.parsers.tinkoff_debit_card import TinkoffDebitCardParser
from core.parsers.vtb_credit_card import VTBCreditCardParser
from core.parsers.vtb_credit_products import VTBCreditProductsParser
from core.parsers.vtb_debit_card import VTBDebitCardParser

# region ================== VTB Parsers ==================


async def run_vtb_debit_card_parser():
    """Запуск парсера VTB дебетовых карт с нормализацией данных."""
    # Парсинг данных
    async with VTBDebitCardParser(headless=False) as parser:
        print("Парсер инициализирован")

        # Парсинг страницы с дебетовыми картами
        url = "https://www.vtb.ru/personal/karty/debetovye/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено карт: {data.get('cards_count')}")
    print("Начинаю нормализацию данных с помощью GigaChat...")

    try:
        normalizer = GigaChatNormalizer()
        normalized_cards = await normalizer.normalize_batch(
            items=data.get("cards", []),
            schema=DEBIT_CARD_SCHEMA,
            description=(
                "Нормализация данных дебетовых карт ВТБ. "
                "Особое внимание удели полю 'features' - извлеки все особенности карты "
                "с их значениями и описаниями. Убери лишний текст из значений."
            ),
        )

        # Обновляем данные нормализованными картами
        data["cards"] = normalized_cards
        print(f"Нормализация завершена. Обработано {len(normalized_cards)} карт\n")

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено карт: {data.get('cards_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждой карте
    for idx, card in enumerate(data.get("cards", []), 1):
        print(f"Карта {idx}:")
        print(f"  Название: {card.get('title', 'N/A')}")
        print(f"  Описание: {card.get('description', 'N/A')}")
        if card.get("badge"):
            print(f"  Бейдж: {card.get('badge')}")
        if card.get("features"):
            print("  Особенности:")
            for feature in card.get("features", []):
                print(
                    f"    - {feature.get('value', 'N/A')}: {feature.get('label', 'N/A')}"
                )
        print(f"  Ссылка на оформление: {card.get('apply_link', 'N/A')}")
        print(f"  Ссылка на подробности: {card.get('details_link', 'N/A')}")
        if "error" in card:
            print(f"Ошибка нормализации: {card.get('error')}")
        print()


async def run_vtb_credit_card_parser():
    """Запуск парсера VTB кредитных карт с нормализацией данных."""
    # Парсинг данных
    async with VTBCreditCardParser(headless=False) as parser:
        print("Парсер кредитных карт инициализирован")

        # Парсинг страницы с кредитными картами
        url = "https://www.vtb.ru/personal/karty/kreditnye/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено карт: {data.get('cards_count')}")
    print("Начинаю нормализацию данных о кредитных картах с помощью GigaChat...")

    try:
        normalizer = GigaChatNormalizer()
        normalized_cards = await normalizer.normalize_batch(
            items=data.get("cards", []),
            schema=CREDIT_CARD_SCHEMA,
            description=(
                "Нормализация данных кредитных карт ВТБ. "
                "Извлеки все числовые значения и единицы измерения для полей в 'features'. "
                "Убери лишний текст из значений особенностей."
            ),
        )

        # Обновляем данные нормализованными картами
        data["cards"] = normalized_cards
        print(f"Нормализация завершена. Обработано {len(normalized_cards)} карт\n")

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено карт: {data.get('cards_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждой карте
    for idx, card in enumerate(data.get("cards", []), 1):
        print(f"Карта {idx}:")
        print(f"  Название: {card.get('title', 'N/A')}")
        if card.get("description"):
            print(f"  Описание: {card.get('description')}")
        if card.get("features"):
            print("  Особенности:")
            for feature in card.get("features", []):
                print(
                    f"    - {feature.get('value', 'N/A')}: {feature.get('label', 'N/A')}"
                )
        if card.get("apply_link"):
            print(f"  Ссылка на оформление: {card.get('apply_link')}")
        if card.get("details_link"):
            print(f"  Ссылка на подробности: {card.get('details_link')}")
        if "error" in card:
            print(f"Ошибка нормализации: {card.get('error')}")
        print()


async def run_vtb_credit_products():
    """Запуск парсера VTB кредитов с нормализацией данных."""

    # Парсинг данных
    async with VTBCreditProductsParser(headless=False) as parser:
        print("Парсер инициализирован")

        # Парсинг страницы с кредитными продуктами
        url = "https://www.vtb.ru/malyj-biznes/kredity-i-garantii/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    print(f"\nПарсинг завершен. Найдено продуктов: {data.get('products_count')}")
    print("Начинаю нормализацию данных с помощью GigaChat...")

    try:
        normalizer = GigaChatNormalizer()
        normalized_products = await normalizer.normalize_batch(
            items=data.get("products", []),
            schema=CREDIT_PRODUCT_SCHEMA,
            description=(
                "Нормализация данных кредитных продуктов ВТБ. "
                "Особое внимание удели полю 'price' - извлеки только сумму и единицы измерения, "
                "убери весь лишний текст. Для поля 'term' оставь только информацию о сроке и условиях."
            ),
        )

        # Обновляем данные нормализованными продуктами
        data["products"] = normalized_products
        print(
            f"Нормализация завершена. Обработано {len(normalized_products)} продуктов\n"
        )

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено продуктов: {data.get('products_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждом продукте
    for idx, product in enumerate(data.get("products", []), 1):
        print(f"Продукт {idx}:")
        print(f"  Название: {product.get('title', 'N/A')}")
        print(f"  Описание: {product.get('subtitle', 'N/A')}")
        print(f"  Сумма: {product.get('price', 'N/A')}")
        print(f"  Условия: {product.get('term', 'N/A')}")
        print(f"  Ссылка: {product.get('link', 'N/A')}")
        if "error" in product:
            print(f"Ошибка нормализации: {product.get('error')}")
        print()


# endregion


# region ================== Alpha Bank Parsers ==================
async def run_alpha_debit_card_parser():
    """Запуск парсера Альфа-Банка дебетовых карт с нормализацией данных."""
    # Парсинг данных
    async with AlphaDebitCardParser(headless=False) as parser:
        print("Парсер дебетовых карт Альфа-Банка инициализирован")

        # Парсинг страницы с дебетовыми картами
        url = "https://alfabank.ru/everyday/debit-cards/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено карт: {data.get('cards_count')}")
    print(
        "Начинаю нормализацию данных о дебетовых картах Альфа-Банка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_cards = await normalizer.normalize_batch(
            items=data.get("cards", []),
            schema=DEBIT_CARD_SCHEMA,
            description=(
                "Нормализация данных дебетовых карт Альфа-Банка. "
                "Особое внимание удели полю 'features' - извлеки все особенности карты "
                "с их значениями и описаниями. Убери лишний текст из значений."
            ),
        )

        # Обновляем данные нормализованными картами
        data["cards"] = normalized_cards
        print(f"Нормализация завершена. Обработано {len(normalized_cards)} карт\n")

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено карт: {data.get('cards_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждой карте
    for idx, card in enumerate(data.get("cards", []), 1):
        print(f"Карта {idx}:")
        print(f"  Название: {card.get('title', 'N/A')}")
        print(f"  Описание: {card.get('description', 'N/A')}")
        if card.get("badge"):
            print(f"  Бейдж: {card.get('badge')}")
        if card.get("features"):
            print("  Особенности:")
            for feature in card.get("features", []):
                print(
                    f"    - {feature.get('value', 'N/A')}: {feature.get('label', 'N/A')}"
                )
        print(f"  Ссылка на оформление: {card.get('apply_link', 'N/A')}")
        print(f"  Ссылка на подробности: {card.get('details_link', 'N/A')}")
        if "error" in card:
            print(f"Ошибка нормализации: {card.get('error')}")
        print()


async def run_alpha_credit_card_parser():
    """Запуск парсера Альфа-Банка кредитных карт с нормализацией данных."""
    # Парсинг данных
    async with AlphaCreditCardParser(headless=False) as parser:
        print("Парсер кредитных карт Альфа-Банка инициализирован")

        # Парсинг страницы с кредитными картами
        url = "https://alfabank.ru/get-money/credit-cards/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено карт: {data.get('cards_count')}")
    print(
        "Начинаю нормализацию данных о кредитных картах Альфа-Банка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_cards = await normalizer.normalize_batch(
            items=data.get("cards", []),
            schema=CREDIT_CARD_SCHEMA,
            description=(
                "Нормализация данных кредитных карт Альфа-Банка. "
                "Извлеки все числовые значения и единицы измерения для полей в 'features'. "
                "Убери лишний текст из значений особенностей."
            ),
        )

        # Обновляем данные нормализованными картами
        data["cards"] = normalized_cards
        print(f"Нормализация завершена. Обработано {len(normalized_cards)} карт\n")

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено карт: {data.get('cards_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждой карте
    for idx, card in enumerate(data.get("cards", []), 1):
        print(f"Карта {idx}:")
        print(f"  Название: {card.get('title', 'N/A')}")
        if card.get("description"):
            print(f"  Описание: {card.get('description')}")
        if card.get("features"):
            print("  Особенности:")
            for feature in card.get("features", []):
                print(
                    f"    - {feature.get('value', 'N/A')}: {feature.get('label', 'N/A')}"
                )
        if card.get("apply_link"):
            print(f"  Ссылка на оформление: {card.get('apply_link')}")
        if card.get("details_link"):
            print(f"  Ссылка на подробности: {card.get('details_link')}")
        if "error" in card:
            print(f"Ошибка нормализации: {card.get('error')}")
        print()


async def run_alpha_credit_products_parser():
    """Запуск парсера Альфа-Банка кредитных продуктов с нормализацией данных."""
    # Парсинг данных
    async with AlphaCreditProductsParser(headless=False) as parser:
        print("Парсер кредитных продуктов Альфа-Банка инициализирован")

        # Парсинг страницы с кредитными продуктами
        url = "https://alfabank.ru/get-money/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено продуктов: {data.get('products_count')}")
    print(
        "Начинаю нормализацию данных о кредитных продуктах Альфа-Банка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_products = await normalizer.normalize_batch(
            items=data.get("products", []),
            schema=CREDIT_PRODUCT_SCHEMA,
            description=(
                "Нормализация данных кредитных продуктов Альфа-Банка. "
                "Особое внимание удели полю 'price' - извлеки только сумму и единицы измерения, "
                "убери весь лишний текст. Для поля 'term' оставь только информацию о сроке и условиях."
            ),
        )

        # Обновляем данные нормализованными продуктами
        data["products"] = normalized_products
        print(
            f"Нормализация завершена. Обработано {len(normalized_products)} продуктов\n"
        )

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено продуктов: {data.get('products_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждом продукте
    for idx, product in enumerate(data.get("products", []), 1):
        print(f"Продукт {idx}:")
        print(f"  Название: {product.get('title', 'N/A')}")
        print(f"  Описание: {product.get('subtitle', 'N/A')}")
        print(f"  Сумма: {product.get('price', 'N/A')}")
        print(f"  Условия: {product.get('term', 'N/A')}")
        print(f"  Ссылка: {product.get('link', 'N/A')}")
        if "error" in product:
            print(f"Ошибка нормализации: {product.get('error')}")
        print()


# endregion


# region ================== TBank Parsers ==================


async def run_tinkoff_debit_card_parser():
    """Запуск парсера Тинькофф Банка дебетовых карт с нормализацией данных."""
    # Парсинг данных
    async with TinkoffDebitCardParser(headless=False) as parser:
        print("Парсер дебетовых карт Тинькофф Банка инициализирован")

        # Парсинг страницы с дебетовыми картами
        url = "https://www.tbank.ru/cards/debit-cards/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено карт: {data.get('cards_count')}")
    print(
        "Начинаю нормализацию данных о дебетовых картах Тинькофф Банка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_cards = await normalizer.normalize_batch(
            items=data.get("cards", []),
            schema=DEBIT_CARD_SCHEMA,
            description=(
                "Нормализация данных дебетовых карт Тинькофф Банка. "
                "Особое внимание удели полю 'features' - извлеки все особенности карты "
                "с их значениями и описаниями. Убери лишний текст из значений."
            ),
        )

        # Обновляем данные нормализованными картами
        data["cards"] = normalized_cards
        print(f"Нормализация завершена. Обработано {len(normalized_cards)} карт\n")

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено карт: {data.get('cards_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждой карте
    for idx, card in enumerate(data.get("cards", []), 1):
        print(f"Карта {idx}:")
        print(f"  Название: {card.get('title', 'N/A')}")
        print(f"  Описание: {card.get('description', 'N/A')}")
        if card.get("badge"):
            print(f"  Бейдж: {card.get('badge')}")
        if card.get("features"):
            print("  Особенности:")
            for feature in card.get("features", []):
                print(
                    f"    - {feature.get('value', 'N/A')}: {feature.get('label', 'N/A')}"
                )
        print(f"  Ссылка на оформление: {card.get('apply_link', 'N/A')}")
        print(f"  Ссылка на подробности: {card.get('details_link', 'N/A')}")
        if "error" in card:
            print(f"Ошибка нормализации: {card.get('error')}")
        print()


async def run_tinkoff_credit_card_parser():
    """Запуск парсера Тинькофф Банка кредитных карт с нормализацией данных."""
    # Парсинг данных
    async with TinkoffCreditCardParser(headless=False) as parser:
        print("Парсер кредитных карт Тинькофф Банка инициализирован")

        # Парсинг страницы с кредитными картами
        url = "https://www.tbank.ru/cards/credit-cards/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено карт: {data.get('cards_count')}")
    print(
        "Начинаю нормализацию данных о кредитных картах Тинькофф Банка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_cards = await normalizer.normalize_batch(
            items=data.get("cards", []),
            schema=CREDIT_CARD_SCHEMA,
            description=(
                "Нормализация данных кредитных карт Тинькофф Банка. "
                "Извлеки все числовые значения и единицы измерения для полей в 'features'. "
                "Убери лишний текст из значений особенностей."
            ),
        )

        # Обновляем данные нормализованными картами
        data["cards"] = normalized_cards
        print(f"Нормализация завершена. Обработано {len(normalized_cards)} карт\n")

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено карт: {data.get('cards_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждой карте
    for idx, card in enumerate(data.get("cards", []), 1):
        print(f"Карта {idx}:")
        print(f"  Название: {card.get('title', 'N/A')}")
        if card.get("description"):
            print(f"  Описание: {card.get('description')}")
        if card.get("features"):
            print("  Особенности:")
            for feature in card.get("features", []):
                print(
                    f"    - {feature.get('value', 'N/A')}: {feature.get('label', 'N/A')}"
                )
        if card.get("apply_link"):
            print(f"  Ссылка на оформление: {card.get('apply_link')}")
        if card.get("details_link"):
            print(f"  Ссылка на подробности: {card.get('details_link')}")
        if "error" in card:
            print(f"Ошибка нормализации: {card.get('error')}")
        print()


async def run_tinkoff_credit_products_parser():
    """Запуск парсера Тинькофф Банка кредитных продуктов с нормализацией данных."""
    # Парсинг данных
    async with TinkoffCreditProductsParser(headless=False) as parser:
        print("Парсер кредитных продуктов Тинькофф Банка инициализирован")

        # Парсинг страницы с кредитными продуктами
        url = "https://www.tbank.ru/loans/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено продуктов: {data.get('products_count')}")
    print(
        "Начинаю нормализацию данных о кредитных продуктах Тинькофф Банка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_products = await normalizer.normalize_batch(
            items=data.get("products", []),
            schema=CREDIT_PRODUCT_SCHEMA,
            description=(
                "Нормализация данных кредитных продуктов Тинькофф Банка. "
                "Особое внимание удели полю 'price' - извлеки только сумму и единицы измерения, "
                "убери весь лишний текст. Для поля 'term' оставь только информацию о сроке и условиях."
            ),
        )

        # Обновляем данные нормализованными продуктами
        data["products"] = normalized_products
        print(
            f"Нормализация завершена. Обработано {len(normalized_products)} продуктов\n"
        )

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено продуктов: {data.get('products_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждом продукте
    for idx, product in enumerate(data.get("products", []), 1):
        print(f"Продукт {idx}:")
        print(f"  Название: {product.get('title', 'N/A')}")
        print(f"  Описание: {product.get('subtitle', 'N/A')}")
        print(f"  Сумма: {product.get('price', 'N/A')}")
        print(f"  Условия: {product.get('term', 'N/A')}")
        print(f"  Ссылка: {product.get('link', 'N/A')}")
        if "error" in product:
            print(f"Ошибка нормализации: {product.get('error')}")
        print()


# endregion


# region ================== Gazprombank Parsers ==================


async def run_gazprombank_debit_card_parser():
    """Запуск парсера Газпромбанка дебетовых карт с нормализацией данных."""
    # Парсинг данных
    async with GazprombankDebitCardParser(headless=False) as parser:
        print("Парсер дебетовых карт Газпромбанка инициализирован")

        # Парсинг страницы с дебетовыми картами
        url = "https://www.gazprombank.ru/personal/cards/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено карт: {data.get('cards_count')}")
    print(
        "Начинаю нормализацию данных о дебетовых картах Газпромбанка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_cards = await normalizer.normalize_batch(
            items=data.get("cards", []),
            schema=DEBIT_CARD_SCHEMA,
            description=(
                "Нормализация данных дебетовых карт Газпромбанка. "
                "Особое внимание удели полю 'features' - извлеки все особенности карты "
                "с их значениями и описаниями. Убери лишний текст из значений."
            ),
        )

        # Обновляем данные нормализованными картами
        data["cards"] = normalized_cards
        print(f"Нормализация завершена. Обработано {len(normalized_cards)} карт\n")

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено карт: {data.get('cards_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждой карте
    for idx, card in enumerate(data.get("cards", []), 1):
        print(f"Карта {idx}:")
        print(f"  Название: {card.get('title', 'N/A')}")
        print(f"  Описание: {card.get('description', 'N/A')}")
        if card.get("badge"):
            print(f"  Бейдж: {card.get('badge')}")
        if card.get("features"):
            print("  Особенности:")
            for feature in card.get("features", []):
                print(
                    f"    - {feature.get('value', 'N/A')}: {feature.get('label', 'N/A')}"
                )
        print(f"  Ссылка на оформление: {card.get('apply_link', 'N/A')}")
        print(f"  Ссылка на подробности: {card.get('details_link', 'N/A')}")
        if "error" in card:
            print(f"Ошибка нормализации: {card.get('error')}")
        print()


async def run_gazprombank_credit_card_parser():
    """Запуск парсера Газпромбанка кредитных карт с нормализацией данных."""
    # Парсинг данных
    async with GazprombankCreditCardParser(headless=False) as parser:
        print("Парсер кредитных карт Газпромбанка инициализирован")

        # Парсинг страницы с кредитными картами
        url = "https://www.gazprombank.ru/personal/credit-cards/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено карт: {data.get('cards_count')}")
    print(
        "Начинаю нормализацию данных о кредитных картах Газпромбанка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_cards = await normalizer.normalize_batch(
            items=data.get("cards", []),
            schema=CREDIT_CARD_SCHEMA,
            description=(
                "Нормализация данных кредитных карт Газпромбанка. "
                "Извлеки все числовые значения и единицы измерения для полей в 'features'. "
                "Убери лишний текст из значений особенностей."
            ),
        )

        # Обновляем данные нормализованными картами
        data["cards"] = normalized_cards
        print(f"Нормализация завершена. Обработано {len(normalized_cards)} карт\n")

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено карт: {data.get('cards_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждой карте
    for idx, card in enumerate(data.get("cards", []), 1):
        print(f"Карта {idx}:")
        print(f"  Название: {card.get('title', 'N/A')}")
        if card.get("description"):
            print(f"  Описание: {card.get('description')}")
        if card.get("badge"):
            print(f"  Бейдж: {card.get('badge')}")
        if card.get("features"):
            print("  Особенности:")
            for feature in card.get("features", []):
                print(
                    f"    - {feature.get('value', 'N/A')}: {feature.get('label', 'N/A')}"
                )
        if card.get("apply_link"):
            print(f"  Ссылка на оформление: {card.get('apply_link')}")
        if card.get("details_link"):
            print(f"  Ссылка на подробности: {card.get('details_link')}")
        if "error" in card:
            print(f"Ошибка нормализации: {card.get('error')}")
        print()


async def run_gazprombank_credit_products_parser():
    """Запуск парсера Газпромбанка кредитных продуктов с нормализацией данных."""
    # Парсинг данных
    async with GazprombankCreditProductsParser(headless=False) as parser:
        print("Парсер кредитных продуктов Газпромбанка инициализирован")

        # Парсинг страницы с кредитными продуктами
        url = "https://www.gazprombank.ru/personal/take_credit/consumer_credit/"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено продуктов: {data.get('products_count')}")
    print(
        "Начинаю нормализацию данных о кредитных продуктах Газпромбанка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_products = await normalizer.normalize_batch(
            items=data.get("products", []),
            schema=CREDIT_PRODUCT_SCHEMA,
            description=(
                "Нормализация данных кредитных продуктов Газпромбанка. "
                "Особое внимание удели полю 'price' - извлеки только сумму и единицы измерения, "
                "убери весь лишний текст. Для поля 'term' оставь только информацию о сроке и условиях."
            ),
        )

        # Обновляем данные нормализованными продуктами
        data["products"] = normalized_products
        print(
            f"Нормализация завершена. Обработано {len(normalized_products)} продуктов\n"
        )

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено продуктов: {data.get('products_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждом продукте
    for idx, product in enumerate(data.get("products", []), 1):
        print(f"Продукт {idx}:")
        print(f"  Название: {product.get('title', 'N/A')}")
        print(f"  Описание: {product.get('subtitle', 'N/A')}")
        print(f"  Сумма: {product.get('price', 'N/A')}")
        print(f"  Условия: {product.get('term', 'N/A')}")
        print(f"  Ссылка: {product.get('link', 'N/A')}")
        if "error" in product:
            print(f"Ошибка нормализации: {product.get('error')}")
        print()


# endregion


async def run_moex_securities_parser():
    """Запуск парсера ценных бумаг MOEX в интерактивном режиме."""
    async with MoexSecuritiesParser() as parser:
        print("Парсер ценных бумаг MOEX инициализирован")

        # Запуск интерактивного режима
        result = await parser.interactive_parse()

        # Вывод результатов
        if result.get("error"):
            print(f"\nОшибка: {result['error']}")
            return

        print(f"\n{'=' * 60}")
        print("РЕЗУЛЬТАТЫ ПАРСИНГА")
        print(f"{'=' * 60}")

        if result.get("bank_info"):
            print(f"Банк: {result['bank_info']['display']}")

        if result.get("interval"):
            print(f"Интервал свечей: {result['interval']}")

        if result.get("date_from") and result.get("date_till"):
            print(f"Период: {result['date_from']} - {result['date_till']}")

        # Информация о выбранных ценных бумагах
        if result.get("securities_info"):
            securities_info = result["securities_info"]
            print(f"\nОбработано ценных бумаг: {len(securities_info)}")
            for sec_info in securities_info:
                status = "OK" if sec_info.get("rows_count", 0) > 0 else "WARNING"
                print(
                    f"  {status} {sec_info.get('shortname')} ({sec_info.get('secid')}): {sec_info.get('rows_count', 0)} записей"
                )
                if sec_info.get("error"):
                    print(f"    Ошибка: {sec_info['error']}")

        # Вывод датафрейма
        if result.get("candles") is not None and not result["candles"].empty:
            df = result["candles"]
            print(f"\n{'=' * 60}")
            print("ДАТАФРЕЙМ СВЕЧЕЙ")
            print(f"{'=' * 60}")
            print(f"\nВсего записей: {len(df)}")

            # Проверяем наличие всех необходимых столбцов
            required_columns = [
                "open",
                "close",
                "high",
                "low",
                "value",
                "volume",
                "begin",
                "end",
            ]
            available_columns = [col for col in required_columns if col in df.columns]
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                print(f"Отсутствующие столбцы: {missing_columns}")

            print(f"\nДоступные столбцы: {list(df.columns)}")

            # Показываем первые несколько строк
            print("\nПервые 5 строк датафрейма:")
            display_columns = [
                "open",
                "close",
                "high",
                "low",
                "value",
                "volume",
                "begin",
                "end",
            ]
            if "secid" in df.columns:
                display_columns.append("secid")
            if "shortname" in df.columns:
                display_columns.append("shortname")

            # Выбираем только существующие столбцы
            display_columns = [col for col in display_columns if col in df.columns]
            print(df[display_columns].head().to_string())

            # Статистика по данным
            if not df.empty:
                if "begin" in df.columns:
                    print(f"\nПериод данных: {df['begin'].min()} - {df['begin'].max()}")
                if "close" in df.columns:
                    print(f"Минимальная цена закрытия: {df['close'].min():.2f} RUB")
                    print(f"Максимальная цена закрытия: {df['close'].max():.2f} RUB")
                    print(f"Средняя цена закрытия: {df['close'].mean():.2f} RUB")
                    if len(df) > 0:
                        print(f"Последняя цена закрытия: {df['close'].iloc[-1]:.2f} RUB")
                if "volume" in df.columns:
                    print(f"Средний объем торгов: {df['volume'].mean():.0f}")

            # Группировка по ценным бумагам (если обрабатывалось несколько)
            if "secid" in df.columns and df["secid"].nunique() > 1:
                print("\nРаспределение по ценным бумагам:")
                for secid in df["secid"].unique():
                    sec_df = df[df["secid"] == secid]
                    print(f"  {secid}: {len(sec_df)} записей")
        else:
            print("\nДатафрейм пуст или не получен")

        if result.get("charts_generated"):
            print("\nГрафики успешно построены")
        else:
            print("\nГрафики не были построены")

        print(f"{'=' * 60}\n")


# region ================== Sberbank Parsers ==================


async def run_sberbank_debit_card_parser():
    """Запуск парсера Сбербанка дебетовых карт с нормализацией данных.

    Использует парсер на основе Selenium, который работает с существующим профилем
    Chrome пользователя, где уже установлены все сертификаты Минцифры.
    Это решает проблему с сертификатами, которая возникает при использовании Playwright.
    """
    # Используем парсер на основе Selenium для работы с сертификатами
    # Он использует существующий профиль Chrome, где уже установлены сертификаты
    async with SberbankDebitCardSeleniumParser(headless=False) as parser:
        print("Парсер дебетовых карт Сбербанка инициализирован")

        # Парсинг страницы с дебетовыми картами
        url = "https://www.sberbank.ru/ru/person/bank_cards/debit"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено карт: {data.get('cards_count')}")
    print(
        "Начинаю нормализацию данных о дебетовых картах Сбербанка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_cards = await normalizer.normalize_batch(
            items=data.get("cards", []),
            schema=DEBIT_CARD_SCHEMA,
            description=(
                "Нормализация данных дебетовых карт Сбербанка. "
                "Особое внимание удели полю 'features' - извлеки все особенности карты "
                "с их значениями и описаниями. Убери лишний текст из значений."
            ),
        )

        # Обновляем данные нормализованными картами
        data["cards"] = normalized_cards
        print(f"Нормализация завершена. Обработано {len(normalized_cards)} карт\n")

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено карт: {data.get('cards_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждой карте
    for idx, card in enumerate(data.get("cards", []), 1):
        print(f"Карта {idx}:")
        print(f"  Название: {card.get('title', 'N/A')}")
        print(f"  Описание: {card.get('description', 'N/A')}")
        if card.get("badge"):
            print(f"  Бейдж: {card.get('badge')}")
        if card.get("features"):
            print("  Особенности:")
            for feature in card.get("features", []):
                print(
                    f"    - {feature.get('value', 'N/A')}: {feature.get('label', 'N/A')}"
                )
        print(f"  Ссылка на оформление: {card.get('apply_link', 'N/A')}")
        print(f"  Ссылка на подробности: {card.get('details_link', 'N/A')}")
        if "error" in card:
            print(f"Ошибка нормализации: {card.get('error')}")
        print()


async def run_sberbank_credit_card_parser():
    """Запуск парсера Сбербанка кредитных карт с нормализацией данных.

    Использует парсер на основе Selenium, который работает с существующим профилем
    Chrome пользователя, где уже установлены все сертификаты Минцифры.
    Это решает проблему с сертификатами, которая возникает при использовании Playwright.
    """
    # Используем парсер на основе Selenium для работы с сертификатами
    # Он использует существующий профиль Chrome, где уже установлены сертификаты
    async with SberbankCreditCardSeleniumParser(headless=False) as parser:
        print("Парсер кредитных карт Сбербанка инициализирован")

        # Парсинг страницы с кредитными картами
        url = "https://www.sberbank.ru/ru/person/bank_cards/credit_cards"
        print(f"\nПарсинг страницы: {url}")
        data = await parser.parse_page(url)

    # Браузер закрыт, теперь нормализуем данные
    print(f"\nПарсинг завершен. Найдено карт: {data.get('cards_count')}")
    print(
        "Начинаю нормализацию данных о кредитных картах Сбербанка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_cards = await normalizer.normalize_batch(
            items=data.get("cards", []),
            schema=CREDIT_CARD_SCHEMA,
            description=(
                "Нормализация данных кредитных карт Сбербанка. "
                "Особое внимание удели полю 'features' - извлеки все особенности карты "
                "с их значениями и описаниями (например, беспроцентный период, кешбэк, "
                "обслуживание и т.д.). Убери лишний текст из значений."
            ),
        )

        # Обновляем данные нормализованными картами
        data["cards"] = normalized_cards
        print(f"Нормализация завершена. Обработано {len(normalized_cards)} карт\n")

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы: {data.get('title')}")
    print(f"Найдено карт: {data.get('cards_count')}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждой карте
    for idx, card in enumerate(data.get("cards", []), 1):
        print(f"Карта {idx}:")
        print(f"  Название: {card.get('title', 'N/A')}")
        print(f"  Описание: {card.get('description', 'N/A')}")
        if card.get("badge"):
            print(f"  Бейдж: {card.get('badge')}")
        if card.get("features"):
            print("  Особенности:")
            for feature in card.get("features", []):
                print(
                    f"    - {feature.get('value', 'N/A')}: {feature.get('label', 'N/A')}"
                )
        print(f"  Ссылка на оформление: {card.get('apply_link', 'N/A')}")
        print(f"  Ссылка на подробности: {card.get('details_link', 'N/A')}")
        if "error" in card:
            print(f"Ошибка нормализации: {card.get('error')}")
        print()


async def run_sberbank_credit_products_parser():
    """Запуск парсера Сбербанка кредитных продуктов с нормализацией данных.

    Использует парсер на основе Selenium, который работает с существующим профилем
    Chrome пользователя, где уже установлены все сертификаты Минцифры.
    Это решает проблему с сертификатами, которая возникает при использовании Playwright.

    Парсит кредиты наличными и ипотеки:
    - Кредиты: https://www.sberbank.ru/ru/person/credits/money
    - Ипотеки: https://www.sberbank.ru/ru/person/credits/homenew
    """
    # Используем парсер на основе Selenium для работы с сертификатами
    async with SberbankCreditProductsSeleniumParser(headless=False) as parser:
        print("Парсер кредитных продуктов Сбербанка инициализирован")

        # Парсинг страницы с кредитами наличными
        url_credits = "https://www.sberbank.ru/ru/person/credits/money"
        print(f"\nПарсинг страницы: {url_credits}")
        data_credits = await parser.parse_page(url_credits)

        print(
            f"\nПарсинг кредитов завершен. Найдено продуктов: {data_credits.get('products_count')}"
        )

        # Парсинг страницы с ипотеками
        url_home = "https://www.sberbank.ru/ru/person/credits/homenew"
        print(f"\nПарсинг страницы: {url_home}")
        data_home = await parser.parse_page(url_home)

        print(
            f"\nПарсинг ипотек завершен. Найдено продуктов: {data_home.get('products_count')}"
        )

    # Браузер закрыт, теперь нормализуем данные
    # Объединяем продукты с обеих страниц
    all_products = data_credits.get("products", []) + data_home.get("products", [])

    print(f"\nВсего найдено продуктов: {len(all_products)}")
    print(
        "Начинаю нормализацию данных о кредитных продуктах Сбербанка с помощью GigaChat..."
    )

    try:
        normalizer = GigaChatNormalizer()
        normalized_products = await normalizer.normalize_batch(
            items=all_products,
            schema=CREDIT_PRODUCT_SCHEMA,
            description=(
                "Нормализация данных кредитных продуктов Сбербанка. "
                "Особое внимание удели полям 'price' и 'term' - извлеки сумму кредита из price "
                "и срок/условия из term. Убери лишний текст из значений. "
                "Поле 'price' должно содержать сумму с единицами измерения (₽, млн ₽, тыс ₽). "
                "Поле 'term' должно содержать срок и условия кредита."
            ),
        )

        print(
            f"Нормализация завершена. Обработано {len(normalized_products)} продуктов\n"
        )

    except Exception as e:
        print(f"Ошибка при нормализации данных: {e}")
        print("Используются исходные данные без нормализации.\n")
        normalized_products = all_products

    # Вывод результатов
    print(f"{'=' * 60}")
    print(f"Заголовок страницы кредитов: {data_credits.get('title')}")
    print(f"Найдено кредитов: {data_credits.get('products_count')}")
    print(f"Заголовок страницы ипотек: {data_home.get('title')}")
    print(f"Найдено ипотек: {data_home.get('products_count')}")
    print(f"Всего продуктов: {len(normalized_products)}")
    print(f"{'=' * 60}\n")

    # Вывод информации о каждом продукте
    for idx, product in enumerate(normalized_products, 1):
        print(f"Продукт {idx}:")
        print(f"  Название: {product.get('title', 'N/A')}")
        print(f"  Описание: {product.get('subtitle', 'N/A')}")
        print(f"  Сумма: {product.get('price', 'N/A')}")
        print(f"  Условия: {product.get('term', 'N/A')}")
        print(f"  Ссылка: {product.get('link', 'N/A')}")
        if "error" in product:
            print(f"  Ошибка нормализации: {product.get('error')}")
        print()


# endregion


async def run_banki_ratings_parser():
    """Запуск парсера рейтингов банков Banki.ru.

    Парсит таблицу рейтингов банков со всеми страницами.
    """
    url = "https://www.banki.ru/banks/ratings/?sort_param=bankname&date1=2025-12-01&date2=2025-11-01&PAGEN_1=3"

    print("=" * 80)
    print("Парсер рейтингов банков Banki.ru")
    print("=" * 80)
    print(f"URL: {url}\n")

    async with BankiRatingsParser(headless=False) as ratings_parser:
        data = await ratings_parser.parse_page(url)

        print(f"\nПарсинг завершен")
        print(f"  Всего страниц: {data.get('total_pages', 0)}")
        print(f"  Всего банков: {data.get('total_banks', 0)}")

        # Метаданные
        metadata = data.get('metadata', {})
        if metadata:
            print(f"\nМетаданные:")
            if metadata.get('indicator'):
                print(f"  Показатель: {metadata.get('indicator')}")
            if metadata.get('date1'):
                print(f"  Дата 1: {metadata.get('date1', {}).get('display', 'N/A')} ({metadata.get('date1', {}).get('value', 'N/A')})")
            if metadata.get('date2'):
                print(f"  Дата 2: {metadata.get('date2', {}).get('display', 'N/A')} ({metadata.get('date2', {}).get('value', 'N/A')})")
            if metadata.get('region'):
                print(f"  Регион: {metadata.get('region')}")

        # Выводим первые 10 банков для примера
        ratings = data.get('ratings', [])
        if ratings:
            print(f"\nПримеры данных (первые 10 банков):")
            print("-" * 80)
            for i, rating in enumerate(ratings[:10], 1):
                print(f"\n{i}. {rating.get('bank_name', 'N/A')}")
                print(f"   Место в рейтинге: {rating.get('place', 'N/A')}", end="")
                if rating.get('place_change'):
                    change_sign = '+' if rating.get('place_change_type') == 'up' else ''
                    print(f" ({change_sign}{rating.get('place_change')})", end="")
                print()
                print(f"   Лицензия: {rating.get('license_number', 'N/A')}")
                print(f"   Регион: {rating.get('region', 'N/A')}")
                print(f"   Значение (date1): {rating.get('value_date1', 'N/A'):,.0f}" if rating.get('value_date1') else "   Значение (date1): N/A")
                print(f"   Значение (date2): {rating.get('value_date2', 'N/A'):,.0f}" if rating.get('value_date2') else "   Значение (date2): N/A")
                if rating.get('change_absolute') is not None:
                    change_sign = '+' if rating.get('change_type') == 'increase' else ''
                    print(f"   Изменение: {change_sign}{rating.get('change_absolute'):,.0f}", end="")
                    if rating.get('change_percent') is not None:
                        print(f" ({change_sign}{rating.get('change_percent'):.2f}%)")
                    else:
                        print()
                elif rating.get('change_percent') is not None:
                    change_sign = '+' if rating.get('change_type') == 'increase' else ''
                    print(f"   Изменение: {change_sign}{rating.get('change_percent'):.2f}%")

        print(f"\n\nВсего обработано банков: {len(ratings)}")
        print("=" * 80)

        return data


def main():
    try:
        asyncio.run(run_banki_ratings_parser())

    except KeyboardInterrupt:
        print("\nПрервано пользователем")
        sys.exit(0)

    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
