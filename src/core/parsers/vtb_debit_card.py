from typing import Any

from playwright.async_api import Page

from core.parsers.base import BaseParser


class VTBDebitCardParser(BaseParser):
    """
    Парсер дебетовых карт ВТБ для частных лиц.

    Наследуется от BaseParser и реализует специфичную логику парсинга
    страницы с дебетовыми картами ВТБ.
    """

    def __init__(
        self,
        headless: bool = True,
        **kwargs,
    ):
        """
        Инициализация парсера VTB дебетовых карт.

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
        Парсинг страницы с дебетовыми картами ВТБ.

        Args:
            url: URL страницы для парсинга

        Returns:
            Словарь с извлеченными данными о дебетовых картах
        """
        page = self.page

        # Переход на страницу и ожидание полной загрузки DOM
        await page.goto(url, wait_until="domcontentloaded")

        # Ожидание полной загрузки DOM дерева
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_load_state("networkidle")

        # Ожидание появления контейнера с картами
        await page.wait_for_selector("#card-layout", timeout=self._timeout_to_ms())

        # Имитация человеческого поведения
        await self.random_delay(0.5, 1.0)

        # Легкая прокрутка для загрузки lazy-loaded элементов (если есть)
        # Но не полная прокрутка, так как DOM уже загружен
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await self.random_delay(0.3, 0.5)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.random_delay(0.3, 0.5)
        except Exception:
            pass  # Игнорируем ошибки прокрутки

        # Извлечение данных о всех картах
        cards = await self._extract_cards(page)

        return {
            "url": url,
            "title": await page.title(),
            "cards_count": len(cards),
            "cards": cards,
        }

    async def _extract_cards(self, page: Page) -> list[dict[str, Any]]:
        """
        Извлечение данных о всех дебетовых картах.

        Args:
            page: Страница Playwright

        Returns:
            Список словарей с данными о картах
        """
        # Ожидание появления контейнера с картами
        await page.wait_for_selector("#card-layout", timeout=self._timeout_to_ms())
        await self.random_delay(0.5, 1.0)

        # Получение всех карточек
        # Структура: #card-layout > div.card-layout-gridstyles__Item-chips__sc-1gncb43-1
        card_elements = page.locator(
            "#card-layout > div.card-layout-gridstyles__Item-chips__sc-1gncb43-1"
        )

        cards_count = await card_elements.count()
        cards = []

        for i in range(cards_count):
            try:
                card = card_elements.nth(i)

                # Прокрутка к карточке для загрузки, если нужно
                await card.scroll_into_view_if_needed()

                # Извлечение данных из карточки
                card_data = await self._extract_card_data(card)
                if card_data.get("title"):  # Добавляем только если есть название
                    cards.append(card_data)

            except Exception as e:
                # Пропускаем карточку при ошибке, но продолжаем парсинг
                print(f"Ошибка при извлечении карты {i}: {e}")
                continue

        return cards

    async def _extract_card_data(self, card_locator: Any) -> dict[str, Any]:
        """
        Извлечение данных из одной карточки дебетовой карты.

        Args:
            card_locator: Локатор карточки

        Returns:
            Словарь с данными о карте
        """
        card_data: dict[str, Any] = {}

        try:
            # Название карты
            title_locator = card_locator.locator(
                "a.card-link-wrapperstyles__TitleLinkWrapper-card-base__sc-14554l8-1"
            ).first
            if await title_locator.count() > 0:
                title = await title_locator.text_content()
                card_data["title"] = title.strip() if title else None
        except Exception:
            card_data["title"] = None

        try:
            # Описание карты (первый параграф описания в markdown)
            # Ищем первый параграф после заголовка
            description_locator = card_locator.locator(
                "div.markdownstyles__StyledReactMarkdown-foundation-kit__sc-v45gkz-0 > div.typographystyles__Box-foundation-kit__sc-14qzghz-0.eWOQey.markdown-paragraphstyles__ParagraphTypography-foundation-kit__sc-otngat-0"
            ).first
            if await description_locator.count() > 0:
                description = await description_locator.text_content()
                card_data["description"] = description.strip() if description else None
        except Exception:
            card_data["description"] = None

        try:
            # Извлечение всех числовых показателей (кешбэк, стоимость и т.д.)
            numbers_blocks = card_locator.locator(
                "div.numbersstyles__Box-foundation-kit__sc-1xhbrzd-3"
            )
            numbers_count = await numbers_blocks.count()
            features = []

            for j in range(numbers_count):
                try:
                    block = numbers_blocks.nth(j)
                    value_locator = block.locator(
                        "p.numbersstyles__TypographyTitle-foundation-kit__sc-1xhbrzd-4"
                    ).first
                    label_locator = block.locator(
                        "span.numbersstyles__TypographyDescription-foundation-kit__sc-1xhbrzd-5"
                    ).first

                    if (
                        await value_locator.count() > 0
                        and await label_locator.count() > 0
                    ):
                        value = await value_locator.text_content()
                        label = await label_locator.text_content()
                        if value and label:
                            features.append(
                                {
                                    "value": value.strip(),
                                    "label": label.strip(),
                                }
                            )
                except Exception:
                    continue

            card_data["features"] = features if features else None
        except Exception:
            card_data["features"] = None

        try:
            # Бейдж (если есть, например "Лимитированный тираж")
            badge_locator = card_locator.locator(
                "span.badgestyles__Text-foundation-kit__sc-4r2fuw-1"
            ).first
            if await badge_locator.count() > 0:
                badge = await badge_locator.text_content()
                card_data["badge"] = badge.strip() if badge else None
        except Exception:
            card_data["badge"] = None

        try:
            # Ссылка на оформление карты (первая кнопка "Оформить карту", "Оформить стикер" или "Получить карту")
            apply_link_locator = card_locator.locator(
                'a.buttonstyles__LinkBox-foundation-kit__sc-sa2uer-1:has-text("Оформить"), '
                'a.buttonstyles__LinkBox-foundation-kit__sc-sa2uer-1:has-text("Получить")'
            ).first
            if await apply_link_locator.count() > 0:
                apply_link = await apply_link_locator.get_attribute("href")
                if apply_link:
                    if not apply_link.startswith("http"):
                        apply_link = f"https://www.vtb.ru{apply_link}"
                    card_data["apply_link"] = apply_link
        except Exception:
            card_data["apply_link"] = None

        try:
            # Ссылка на подробности о карте
            details_link_locator = card_locator.locator(
                'a.buttonstyles__LinkBox-foundation-kit__sc-sa2uer-1:has-text("Подробнее")'
            ).first
            if await details_link_locator.count() > 0:
                details_link = await details_link_locator.get_attribute("href")
                if details_link:
                    if not details_link.startswith("http"):
                        # Проверяем, не внешняя ли ссылка
                        if not details_link.startswith(
                            "https://"
                        ) and not details_link.startswith("http://"):
                            details_link = f"https://www.vtb.ru{details_link}"
                    card_data["details_link"] = details_link
        except Exception:
            card_data["details_link"] = None

        return card_data
