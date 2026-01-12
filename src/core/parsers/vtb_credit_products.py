from typing import Any

from playwright.async_api import Page

from core.parsers.base import BaseParser


class VTBCreditProductsParser(BaseParser):
    """
    Парсер кредитных продуктов ВТБ для малого бизнеса.

    Наследуется от BaseParser и реализует специфичную логику парсинга
    страницы с кредитными продуктами ВТБ.
    """

    def __init__(
        self,
        headless: bool = True,
        **kwargs,
    ):
        """
        Инициализация парсера VTB кредитов.

        Args:
            headless: Запуск в headless режиме
            **kwargs: Дополнительные параметры для BaseParser
        """
        super().__init__(
            browser_type="chromium",
            headless=headless,
            **kwargs,
        )

    async def parse_page(self, url: str) -> dict[str, Any]:
        """
        Парсинг страницы с кредитными продуктами ВТБ.

        Args:
            url: URL страницы для парсинга

        Returns:
            Словарь с извлеченными данными о кредитных продуктах
        """
        page = self.page

        # Переход на страницу и ожидание полной загрузки DOM
        await page.goto(url, wait_until="domcontentloaded")

        # Ожидание полной загрузки DOM дерева
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_load_state("networkidle")

        # Имитация человеческого поведения
        await self.random_delay(1.0, 2.0)

        # Поиск и прокрутка до кнопки "Показать еще"
        # Ищем кнопку по тексту, который может содержать число в скобках
        show_more_button = page.locator(
            'span.buttonstyles__Content-foundation-kit__sc-sa2uer-0:has-text("Показать еще")'
        ).first

        # Ожидание появления кнопки
        await show_more_button.wait_for(state="visible", timeout=self._timeout_to_ms())

        # Прокрутка до элемента
        await show_more_button.scroll_into_view_if_needed()
        await self.random_delay(0.5, 1.0)

        # Клик по кнопке "Показать еще" для разворачивания всех продуктов
        await show_more_button.click()

        # Ожидание загрузки новых элементов после клика
        await self.random_delay(1.5, 2.5)
        await page.wait_for_load_state("networkidle")

        # Дополнительная проверка, что кнопка исчезла или изменилась
        try:
            await show_more_button.wait_for(
                state="hidden", timeout=self._timeout_to_ms(5.0)
            )
        except Exception:
            # Кнопка может остаться, но изменить текст - это нормально
            pass

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
        # Ожидание появления контейнера с продуктами
        await page.wait_for_selector("#card-layout", timeout=self._timeout_to_ms())
        await self.random_delay(0.5, 1.0)

        # Получение всех карточек продуктов
        # Структура: #card-layout > div.card-layout-gridstyles__Item-chips__sc-1gncb43-1
        product_cards = page.locator(
            "#card-layout > div.card-layout-gridstyles__Item-chips__sc-1gncb43-1"
        )

        products_count = await product_cards.count()
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
                "p.card-tariffstyles__Title-card-tariff__sc-1yfyvnm-19"
            ).first
            if await title_locator.count() > 0:
                title = await title_locator.text_content()
                product_data["title"] = title.strip() if title else None
        except Exception:
            product_data["title"] = None

        try:
            # Подзаголовок/описание
            subtitle_locator = card_locator.locator(
                "div.card-tariffstyles__Subtitle-card-tariff__sc-1yfyvnm-20"
            ).first
            if await subtitle_locator.count() > 0:
                subtitle = await subtitle_locator.text_content()
                product_data["subtitle"] = subtitle.strip() if subtitle else None
        except Exception:
            product_data["subtitle"] = None

        try:
            # Сумма/цена
            price_locator = card_locator.locator(
                "p.card-tariffstyles__NewPriceSpan-card-tariff__sc-1yfyvnm-38"
            ).first
            if await price_locator.count() > 0:
                price = await price_locator.text_content()
                product_data["price"] = price.strip() if price else None
        except Exception:
            product_data["price"] = None

        try:
            # Срок/условия
            term_locator = card_locator.locator(
                "span.card-tariffstyles__NewPriceTerm-card-tariff__sc-1yfyvnm-21"
            ).first
            if await term_locator.count() > 0:
                term = await term_locator.text_content()
                product_data["term"] = term.strip() if term else None
        except Exception:
            product_data["term"] = None

        try:
            # Ссылка на подробности
            link_locator = card_locator.locator(
                "a.buttonstyles__LinkBox-foundation-kit__sc-sa2uer-1"
            ).first
            if await link_locator.count() > 0:
                link = await link_locator.get_attribute("href")
                # Формирование полной ссылки, если она относительная
                if link and not link.startswith("http"):
                    link = f"https://www.vtb.ru{link}"
                product_data["link"] = link
        except Exception:
            product_data["link"] = None

        return product_data
