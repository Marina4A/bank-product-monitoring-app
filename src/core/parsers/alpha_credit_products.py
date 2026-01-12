from typing import Any

from playwright.async_api import Page

from core.parsers.base import BaseParser


class AlphaCreditProductsParser(BaseParser):
    """
    Парсер кредитных продуктов Альфа-Банка для частных лиц.

    Наследуется от BaseParser и реализует специфичную логику парсинга
    страницы с кредитными продуктами Альфа-Банка.
    """

    def __init__(
        self,
        headless: bool = True,
        **kwargs,
    ):
        """
        Инициализация парсера Альфа-Банка кредитных продуктов.

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
        Парсинг страницы с кредитными продуктами Альфа-Банка.

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

        # Ожидание появления контейнера с продуктами
        await page.wait_for_selector("#all", timeout=self._timeout_to_ms())

        # Имитация человеческого поведения
        await self.random_delay(0.5, 1.0)

        # Легкая прокрутка для загрузки lazy-loaded элементов (если есть)
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await self.random_delay(0.3, 0.5)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.random_delay(0.3, 0.5)
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
        await page.wait_for_selector("#all", timeout=self._timeout_to_ms())
        await self.random_delay(0.5, 1.0)

        # Ищем CatalogCard внутри контейнера #all
        product_cards = page.locator('#all div[data-widget-name="CatalogCard"]')
        products_count = await product_cards.count()

        if products_count == 0:
            # Пробуем найти через Block
            block_elements = page.locator('#all > div[data-widget-name="Block"]')
            blocks_count = await block_elements.count()

            # Ищем CatalogCard внутри каждого Block
            for i in range(min(blocks_count, 10)):  # Проверяем первые 10
                try:
                    block = block_elements.nth(i)
                    catalog_card = block.locator('div[data-widget-name="CatalogCard"]')
                    if await catalog_card.count() > 0:
                        # Используем этот селектор
                        product_cards = page.locator(
                            '#all div[data-widget-name="CatalogCard"]'
                        )
                        products_count = await product_cards.count()
                        break
                except Exception:
                    continue

        if products_count == 0:
            return []

        products = []

        for i in range(products_count):
            try:
                card = product_cards.nth(i)

                # Прокрутка к карточке для загрузки, если нужно
                await card.scroll_into_view_if_needed()

                # Извлечение данных из карточки
                product_data = await self._extract_product_data(card)
                if product_data.get("title"):  # Добавляем только если есть название
                    products.append(product_data)

            except Exception as e:
                # Пропускаем карточку при ошибке, но продолжаем парсинг
                print(f"Ошибка при извлечении продукта {i}: {e}")
                continue

        return products

    async def _extract_product_data(self, card_locator: Any) -> dict[str, Any]:
        """
        Извлечение данных из одной карточки продукта.

        Args:
            card_locator: Локатор карточки продукта

        Returns:
            Словарь с данными о продукте
        """
        product_data: dict[str, Any] = {}

        try:
            # Название продукта
            title_locator = card_locator.locator(
                "h2 > span > a.aXYDeT.gXYDeT.cXYDeT"
            ).first
            if await title_locator.count() > 0:
                title = await title_locator.text_content()
                product_data["title"] = title.strip() if title else None
            else:
                # Альтернативный вариант - просто h2
                title_locator_alt = card_locator.locator("h2").first
                if await title_locator_alt.count() > 0:
                    title = await title_locator_alt.text_content()
                    if title:
                        product_data["title"] = title.strip()
                    else:
                        # Пробуем найти текст в ссылке внутри h2
                        title_link = card_locator.locator("h2 a").first
                        if await title_link.count() > 0:
                            title = await title_link.text_content()
                            product_data["title"] = title.strip() if title else None
        except Exception:
            product_data["title"] = None

        try:
            # Описание продукта
            subtitle_locator = card_locator.locator("p.aR7Oy1.nQWkTE.RQWkTE").first
            if await subtitle_locator.count() > 0:
                subtitle = await subtitle_locator.text_content()
                product_data["subtitle"] = subtitle.strip() if subtitle else None
        except Exception:
            product_data["subtitle"] = None

        try:
            # Извлечение особенностей (price и term)
            # Блоки с особенностями находятся в div[data-test-id="grid"] с классом aUl5hC fUl5hC vQWkTE
            features_container = card_locator.locator(
                'div[data-test-id="grid"].aUl5hC.fUl5hC.vQWkTE'
            ).first
            price = None
            term = None

            if await features_container.count() > 0:
                # Ищем все блоки с особенностями внутри контейнера
                feature_blocks = features_container.locator("div.kUl5hC.lUl5hC")
                blocks_count = await feature_blocks.count()

                for j in range(blocks_count):
                    try:
                        block = feature_blocks.nth(j)
                        # Пропускаем пустые блоки-разделители
                        style_attr = await block.get_attribute("style")
                        if style_attr and "width:0px" in style_attr:
                            continue

                        # Значение особенности (большой текст)
                        value_locator = block.locator(
                            "p.aR7Oy1.yR7Oy1.MR7Oy1.UR7Oy1.nQWkTE.TQWkTE"
                        ).first
                        # Описание особенности (маленький текст)
                        label_locator = block.locator(
                            "p.aR7Oy1.VR7Oy1.nQWkTE.RQWkTE"
                        ).first

                        if (
                            await value_locator.count() > 0
                            and await label_locator.count() > 0
                        ):
                            value = await value_locator.text_content()
                            label = await label_locator.text_content()
                            if value and label:
                                value_text = value.strip()
                                label_text = label.strip().lower()
                                value_text_lower = value_text.lower()

                                # Определяем, что это - price или term
                                # Приоритет отдаем значению (value), так как оно более точно

                                # Проверяем, является ли это суммой
                                is_price = (
                                    # Ключевые слова в значении (приоритет)
                                    any(
                                        keyword in value_text_lower
                                        for keyword in ["₽", "млн", "тыс", "руб", "000"]
                                    )
                                    # Или ключевые слова в описании
                                    or any(
                                        keyword in label_text
                                        for keyword in [
                                            "сумма",
                                            "кредит",
                                            "лимит",
                                            "млн",
                                            "тыс",
                                            "₽",
                                            "руб",
                                        ]
                                    )
                                )

                                # Проверяем, является ли это сроком
                                is_term = (
                                    # Ключевые слова в значении (приоритет)
                                    any(
                                        keyword in value_text_lower
                                        for keyword in [
                                            "лет",
                                            "год",
                                            "месяц",
                                            "дней",
                                            "день",
                                        ]
                                    )
                                    # Или ключевые слова в описании
                                    or any(
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
            # Ссылка на подробности
            # Ищем кнопку "Подробнее"
            details_link_locator = card_locator.locator(
                'a.button__secondary:has-text("Подробнее")'
            ).first
            if await details_link_locator.count() > 0:
                link = await details_link_locator.get_attribute("href")
                if link:
                    if not link.startswith("http"):
                        link = f"https://alfabank.ru{link}"
                    product_data["link"] = link
            else:
                # Альтернативный вариант - ссылка из названия
                title_link = card_locator.locator("h2 a").first
                if await title_link.count() > 0:
                    link = await title_link.get_attribute("href")
                    if link:
                        if not link.startswith("http"):
                            link = f"https://alfabank.ru{link}"
                        product_data["link"] = link
        except Exception:
            product_data["link"] = None

        return product_data
