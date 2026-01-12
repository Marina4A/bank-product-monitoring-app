import asyncio
from typing import Any

from playwright.async_api import Page

from core.parsers.base import BaseParser


class TinkoffCreditProductsParser(BaseParser):
    """
    Парсер кредитных продуктов Тинькофф Банка для частных лиц.

    Наследуется от BaseParser и реализует специфичную логику парсинга
    страницы с кредитными продуктами Тинькофф Банка.
    """

    def __init__(
        self,
        headless: bool = True,
        **kwargs,
    ):
        """
        Инициализация парсера Тинькофф Банка кредитных продуктов.

        Args:
            headless: Запуск в headless режиме
            **kwargs: Дополнительные параметры для BaseParser
        """
        # Убеждаемся, что используется десктопный viewport
        kwargs.setdefault("viewport_width", 1920)
        kwargs.setdefault("viewport_height", 1080)

        super().__init__(
            browser_type="chromium",
            headless=headless,
            **kwargs,
        )

    async def parse_page(self, url: str) -> dict[str, Any]:
        """
        Парсинг страницы с кредитными продуктами Тинькофф Банка.

        Args:
            url: URL страницы для парсинга

        Returns:
            Словарь с извлеченными данными о кредитных продуктах
        """
        page = self.page

        # Убеждаемся, что viewport десктопный
        await page.set_viewport_size({"width": 1920, "height": 1080})

        # Устанавливаем десктопный user agent через переопределение navigator
        # Это нужно сделать ДО загрузки страницы, чтобы сайт определил десктопную версию
        desktop_ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )

        # Переопределяем navigator.userAgent и navigator.platform для гарантии десктопной версии
        await page.add_init_script(f"""
            Object.defineProperty(navigator, 'userAgent', {{
                get: () => '{desktop_ua}'
            }});
            Object.defineProperty(navigator, 'platform', {{
                get: () => 'Win32'
            }});
        """)

        # Переход на страницу и ожидание полной загрузки DOM
        await page.goto(url, wait_until="domcontentloaded")

        # Ожидание полной загрузки DOM дерева
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_load_state("networkidle")

        # Имитация человеческого поведения
        await self.random_delay(0.5, 1.0)

        # Легкая прокрутка для загрузки lazy-loaded элементов (если есть)
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await self.random_delay(0.3, 0.5)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.random_delay(0.3, 0.5)
            # Возвращаемся наверх для начала парсинга
            await page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass  # Игнорируем ошибки прокрутки

        # Извлечение данных о всех продуктах
        products = await self._extract_products(page)

        return {
            "url": url,
            "title": await page.title(),
            "products_count": len(products),
            "products": products,
        }

    async def _extract_products(self, page: Page) -> list[dict[str, Any]]:
        """
        Извлечение данных о всех кредитных продуктах.

        Args:
            page: Страница Playwright

        Returns:
            Список словарей с данными о продуктах
        """
        await self.random_delay(0.3, 0.5)

        # Ожидаем появления контейнеров с продуктами
        try:
            await page.wait_for_selector(
                'div[data-test="atom-container"]', timeout=self._timeout_to_ms(5.0)
            )
        except Exception:
            pass

        # Ищем карточки продуктов по селектору - контейнер с data-test="atom-container"
        product_elements = page.locator('div[data-test="atom-container"]')
        products_count = await product_elements.count()

        if products_count == 0:
            # Пробуем найти через заголовки
            title_elements = page.locator('h2[data-test="htmlTag title"]')
            title_count = await title_elements.count()
            if title_count > 0:
                # Используем селектор с :has() для фильтрации контейнеров с заголовками
                product_elements = page.locator(
                    'div[data-test="atom-container"]:has(h2[data-test="htmlTag title"])'
                )
                products_count = await product_elements.count()

            if products_count == 0:
                return []

        products = []

        for i in range(products_count):
            try:
                product = product_elements.nth(i)

                # Быстрая проверка наличия названия ДО всех остальных операций
                title_locator = product.locator('h2[data-test="htmlTag title"]').first
                if await title_locator.count() == 0:
                    # Пропускаем контейнеры без названия
                    continue

                # Фильтрация: пропускаем информационные блоки без списка преимуществ
                # Реальные кредитные продукты должны иметь список особенностей (advantages)
                advantages_container = product.locator(
                    'ul[data-schema-path="advantages.list"]'
                ).first
                if await advantages_container.count() == 0:
                    # Пропускаем блоки без списка преимуществ (например, калькуляторы, информационные блоки)
                    continue

                # Дополнительная фильтрация по ключевым словам в заголовке
                try:
                    title_text = await title_locator.text_content()
                    if title_text:
                        title_lower = title_text.lower()
                        # Пропускаем информационные блоки с ключевыми словами
                        exclude_keywords = [
                            "узнайте",
                            "калькулятор",
                            "рассчитать",
                            "выберите",
                            "укажите",
                        ]
                        if any(keyword in title_lower for keyword in exclude_keywords):
                            continue
                except Exception:
                    pass

                # Прокрутка к продукту для загрузки, если нужно (с коротким таймаутом)
                try:
                    await asyncio.wait_for(
                        product.scroll_into_view_if_needed(), timeout=2.0
                    )
                except (Exception, asyncio.TimeoutError):
                    # Если не удалось прокрутить за 2 секунды, продолжаем
                    pass

                # Извлечение данных из продукта
                product_data = await self._extract_product_data(product)

                if product_data.get("title"):  # Добавляем только если есть название
                    products.append(product_data)

            except Exception:
                # Пропускаем продукт при ошибке, но продолжаем парсинг
                continue

        return products

    async def _extract_product_data(self, product_locator: Any) -> dict[str, Any]:
        """
        Извлечение данных из одной карточки кредитного продукта.

        Args:
            product_locator: Локатор карточки продукта

        Returns:
            Словарь с данными о продукте
        """
        product_data: dict[str, Any] = {}

        try:
            # Название продукта - h2 с data-test="htmlTag title"
            title_locator = product_locator.locator(
                'h2[data-test="htmlTag title"]'
            ).first
            if await title_locator.count() > 0:
                # Ищем текст в параграфе внутри h2
                title_p = title_locator.locator("p").first
                if await title_p.count() > 0:
                    title = await title_p.text_content()
                    product_data["title"] = title.strip() if title else None
                else:
                    # Если нет параграфа, берем текст напрямую из h2
                    title = await title_locator.text_content()
                    product_data["title"] = title.strip() if title else None
        except Exception:
            product_data["title"] = None

        try:
            # Описание продукта - div с data-test="htmlTag subtitle"
            subtitle_locator = product_locator.locator(
                'div[data-test="htmlTag subtitle"]'
            ).first
            if await subtitle_locator.count() > 0:
                # Ищем текст в параграфе внутри subtitle
                subtitle_p = subtitle_locator.locator("p").first
                if await subtitle_p.count() > 0:
                    subtitle = await subtitle_p.text_content()
                    product_data["subtitle"] = subtitle.strip() if subtitle else None
                else:
                    # Если нет параграфа, берем текст напрямую
                    subtitle = await subtitle_locator.text_content()
                    product_data["subtitle"] = subtitle.strip() if subtitle else None
        except Exception:
            product_data["subtitle"] = None

        try:
            # Извлечение особенностей (advantages) - ul с data-schema-path="advantages.list"
            features_container = product_locator.locator(
                'ul[data-schema-path="advantages.list"]'
            ).first
            price = None
            term = None

            if await features_container.count() > 0:
                # Ищем все элементы li с data-item-type="advantageItem"
                feature_items = features_container.locator(
                    'li[data-item-type="advantageItem"]'
                )
                items_count = await feature_items.count()

                for j in range(items_count):
                    try:
                        item = feature_items.nth(j)

                        # Заголовок особенности (value) - div[data-item-type="advantageTitle"] > h4 > p
                        value_locator = item.locator(
                            'div[data-item-type="advantageTitle"] h4[data-test="htmlTag advantages_list_title"] p'
                        ).first
                        value_count = await value_locator.count()
                        # Если нет параграфа, берем напрямую из h4
                        if value_count == 0:
                            value_locator = item.locator(
                                'div[data-item-type="advantageTitle"] h4[data-test="htmlTag advantages_list_title"]'
                            ).first
                            value_count = await value_locator.count()

                        # Подзаголовок особенности (label) - div[data-item-type="advantageSubtitle"] > div > p
                        label_locator = item.locator(
                            'div[data-item-type="advantageSubtitle"] div[data-test="htmlTag advantages_list_subtitle"] p'
                        ).first
                        label_count = await label_locator.count()
                        # Если нет параграфа, берем напрямую из div
                        if label_count == 0:
                            label_locator = item.locator(
                                'div[data-item-type="advantageSubtitle"] div[data-test="htmlTag advantages_list_subtitle"]'
                            ).first
                            label_count = await label_locator.count()

                        if value_count > 0 and label_count > 0:
                            value = await value_locator.text_content()
                            label = await label_locator.text_content()
                            if value and label:
                                value_text = value.strip()
                                label_text = label.strip().lower()
                                value_text_lower = value_text.lower()

                                # Определяем, что это - price или term
                                # Проверяем, является ли это суммой
                                is_price = any(
                                    keyword in value_text_lower
                                    for keyword in [
                                        "₽",
                                        "млн",
                                        "тыс",
                                        "руб",
                                        "000",
                                        "бесплатно",
                                    ]
                                ) or any(
                                    keyword in label_text
                                    for keyword in [
                                        "сумма",
                                        "кредит",
                                        "лимит",
                                        "млн",
                                        "тыс",
                                        "₽",
                                        "руб",
                                        "деньги",
                                    ]
                                )

                                # Проверяем, является ли это сроком
                                is_term = any(
                                    keyword in value_text_lower
                                    for keyword in [
                                        "лет",
                                        "год",
                                        "месяц",
                                        "дней",
                                        "день",
                                    ]
                                ) or any(
                                    keyword in label_text
                                    for keyword in [
                                        "срок",
                                        "лет",
                                        "год",
                                        "месяц",
                                        "дней",
                                        "день",
                                    ]
                                )

                                # Если это сумма и еще не найдена
                                if is_price and not price:
                                    price = value_text
                                # Если это срок и еще не найден
                                elif is_term and not term:
                                    term = value_text

                    except Exception:
                        continue

            product_data["price"] = price
            product_data["term"] = term
        except Exception:
            product_data["price"] = None
            product_data["term"] = None

        try:
            # Ссылка на оформление или подробности
            # Приоритет: сначала пробуем primary кнопку (оформление), затем flat (подробности)
            apply_link_locator = product_locator.locator(
                'a[data-qa-type="tui/button"][data-appearance="primary"]'
            ).first
            if await apply_link_locator.count() > 0:
                link = await apply_link_locator.get_attribute("href")
                if link:
                    if not link.startswith("http"):
                        link = f"https://www.tbank.ru{link}"
                    product_data["link"] = link
            else:
                # Если нет primary, пробуем flat (подробности)
                details_link_locator = product_locator.locator(
                    'a[data-qa-type="tui/button"][data-appearance="flat"]'
                ).first
                if await details_link_locator.count() > 0:
                    link = await details_link_locator.get_attribute("href")
                    if link:
                        if not link.startswith("http"):
                            link = f"https://www.tbank.ru{link}"
                        product_data["link"] = link
                else:
                    # Альтернативный вариант - ссылка из заголовка (h2 может быть внутри <a>)
                    # Ищем ссылку, содержащую заголовок
                    title_link = product_locator.locator(
                        'a:has(h2[data-test="htmlTag title"])'
                    ).first
                    if await title_link.count() == 0:
                        # Если не нашли, пробуем найти любую ссылку на кредиты
                        title_link = product_locator.locator('a[href*="/loans/"]').first

                    if await title_link.count() > 0:
                        link = await title_link.get_attribute("href")
                        if link:
                            if not link.startswith("http"):
                                link = f"https://www.tbank.ru{link}"
                            product_data["link"] = link
        except Exception:
            product_data["link"] = None

        return product_data
