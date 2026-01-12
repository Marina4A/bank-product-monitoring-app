from typing import Any

from playwright.async_api import Page

from core.parsers.base import BaseParser


class TinkoffDebitCardParser(BaseParser):
    """
    Парсер дебетовых карт Тинькофф Банка для частных лиц.

    Наследуется от BaseParser и реализует специфичную логику парсинга
    страницы с дебетовыми картами Тинькофф Банка.
    """

    def __init__(
        self,
        headless: bool = True,
        **kwargs,
    ):
        """
        Инициализация парсера Тинькофф Банка дебетовых карт.

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
        Парсинг страницы с дебетовыми картами Тинькофф Банка.

        Args:
            url: URL страницы для парсинга

        Returns:
            Словарь с извлеченными данными о дебетовых картах
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
        await self.random_delay(0.5, 1.0)

        # Ищем карточки по правильному селектору - контейнер с data-test="atom-container"
        card_elements = page.locator('div[data-test="atom-container"]')
        cards_count = await card_elements.count()

        if cards_count == 0:
            print("Карты не найдены по селектору div[data-test='atom-container']")
            return []

        cards = []

        for i in range(cards_count):
            try:
                card = card_elements.nth(i)

                # Прокрутка к карточке для загрузки, если нужно
                await card.scroll_into_view_if_needed()

                # Проверяем, не является ли карта архивной
                is_archived, _ = await self._is_archived_card(card)
                if is_archived:
                    continue

                # Извлечение данных из карточки
                card_data = await self._extract_card_data(card)

                if card_data.get("title"):  # Добавляем только если есть название
                    cards.append(card_data)

            except Exception:
                # Пропускаем карточку при ошибке, но продолжаем парсинг
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
            # Название карты - h3 с data-test="htmlTag title"
            title_locator = card_locator.locator('h3[data-test="htmlTag title"]').first
            if await title_locator.count() > 0:
                title = await title_locator.text_content()
                card_data["title"] = title.strip() if title else None
            else:
                # Альтернативный вариант
                title_locator = card_locator.locator("h3").first
                if await title_locator.count() > 0:
                    title = await title_locator.text_content()
                    card_data["title"] = title.strip() if title else None
        except Exception:
            card_data["title"] = None

        try:
            # Описание карты - div с data-test="htmlTag subtitle"
            description_locator = card_locator.locator(
                'div[data-test="htmlTag subtitle"]'
            ).first
            if await description_locator.count() > 0:
                description = await description_locator.text_content()
                card_data["description"] = description.strip() if description else None
            else:
                # Альтернативный вариант - ищем параграф внутри subtitle
                description_locator = card_locator.locator(
                    'div[data-test="htmlTag subtitle"] p'
                ).first
                if await description_locator.count() > 0:
                    description = await description_locator.text_content()
                    card_data["description"] = (
                        description.strip() if description else None
                    )
        except Exception:
            card_data["description"] = None

        try:
            # Извлечение всех особенностей (advantages) - ul с data-schema-path="advantages.list"
            features_container = card_locator.locator(
                'ul[data-schema-path="advantages.list"]'
            ).first
            features = []

            if await features_container.count() > 0:
                # Ищем все элементы li с data-item-type="advantageItem"
                feature_items = features_container.locator(
                    'li[data-item-type="advantageItem"]'
                )
                items_count = await feature_items.count()

                for j in range(items_count):
                    try:
                        item = feature_items.nth(j)

                        # Заголовок особенности (value) - div[data-item-type="advantageTitle"]
                        value_locator = item.locator(
                            'div[data-item-type="advantageTitle"]'
                        ).first
                        # Подзаголовок особенности (label) - div[data-item-type="advantageSubtitle"]
                        label_locator = item.locator(
                            'div[data-item-type="advantageSubtitle"]'
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
            # Бейдж - span с data-qa-type="tui/badge"
            badge_locator = card_locator.locator('span[data-qa-type="tui/badge"]').first
            if await badge_locator.count() > 0:
                # Текст бейджа находится в span.bbD9GgLrL
                badge_text_locator = badge_locator.locator("span.bbD9GgLrL").first
                if await badge_text_locator.count() > 0:
                    badge = await badge_text_locator.text_content()
                    card_data["badge"] = badge.strip() if badge else None
                else:
                    badge = await badge_locator.text_content()
                    card_data["badge"] = badge.strip() if badge else None
            else:
                card_data["badge"] = None
        except Exception:
            card_data["badge"] = None

        try:
            # Ссылка на оформление карты - a с data-qa-type="tui/button" и data-appearance="primary"
            apply_link_locator = card_locator.locator(
                'a[data-qa-type="tui/button"][data-appearance="primary"]'
            ).first
            if await apply_link_locator.count() > 0:
                apply_link = await apply_link_locator.get_attribute("href")
                if apply_link:
                    if not apply_link.startswith("http"):
                        apply_link = f"https://www.tbank.ru{apply_link}"
                    card_data["apply_link"] = apply_link
        except Exception:
            card_data["apply_link"] = None

        try:
            # Ссылка на подробности о карте - a с data-qa-type="tui/button" и data-appearance="flat"
            details_link_locator = card_locator.locator(
                'a[data-qa-type="tui/button"][data-appearance="flat"]'
            ).first
            if await details_link_locator.count() > 0:
                details_link = await details_link_locator.get_attribute("href")
                if details_link:
                    if not details_link.startswith("http"):
                        details_link = f"https://www.tbank.ru{details_link}"
                    card_data["details_link"] = details_link
        except Exception:
            card_data["details_link"] = None

        return card_data

    async def _is_archived_card(self, card_locator: Any) -> tuple[bool, str]:
        """
        Проверка, является ли карта архивной.

        Архивные карты не имеют кнопок оформления или имеют специальные метки.

        Args:
            card_locator: Локатор карточки

        Returns:
            Кортеж (True если карта архивная, строка с отладочной информацией)
        """
        try:
            # Проверяем наличие кнопок оформления
            buttons_info = await card_locator.evaluate("""
                (element) => {
                    const buttons = element.querySelectorAll('button, a[class*="button"], a[class*="primary"]');
                    const result = [];
                    for (let btn of buttons) {
                        const className = btn.className || '';
                        const isPrimary = className.includes('primary') ||
                                         className.includes('apply') ||
                                         className.includes('order');
                        if (isPrimary) {
                            const text = btn.innerText || btn.textContent || '';
                            result.push({
                                isPrimary: true,
                                text: text.trim(),
                                className: className
                            });
                        }
                    }
                    return result;
                }
            """)

            # Ключевые слова для кнопок заказа
            order_keywords = [
                "заказать карту",
                "получить карту",
                "оформить карту",
                "заказать",
                "получить",
                "оформить",
                "применить",
            ]

            has_order_button = False
            found_button_texts = []

            # Проверяем найденные primary кнопки
            for btn_info in buttons_info:
                if btn_info.get("isPrimary"):
                    btn_text = btn_info.get("text", "")
                    found_button_texts.append(btn_text)
                    btn_text_lower = btn_text.lower()

                    # Проверяем наличие ключевых слов для кнопки заказа
                    if any(keyword in btn_text_lower for keyword in order_keywords):
                        has_order_button = True
                        break

            # Если НЕТ кнопки "Заказать" - это может быть архивная карта
            if not has_order_button:
                # Дополнительная проверка: наличие слова "архив" в тексте карточки
                try:
                    card_text = await card_locator.text_content()
                    if card_text:
                        card_text_lower = card_text.lower()
                        archive_keywords = [
                            "архив",
                            "архивная",
                            "архивный",
                            "недоступна",
                            "снята с производства",
                        ]
                        if any(
                            keyword in card_text_lower for keyword in archive_keywords
                        ):
                            return True, ""
                except Exception:
                    pass

                # Если нет кнопки и нет явных признаков архива, считаем карту актуальной
                # (лучше включить, чем исключить)
                return False, ""

            # Дополнительная проверка: наличие слова "архив" в тексте карточки
            try:
                card_text = await card_locator.text_content()
                if card_text:
                    card_text_lower = card_text.lower()
                    archive_keywords = [
                        "архив",
                        "архивная",
                        "архивный",
                        "недоступна",
                        "снята с производства",
                    ]
                    if any(keyword in card_text_lower for keyword in archive_keywords):
                        return True, ""
            except Exception:
                pass

        except Exception:
            # В случае ошибки считаем карту актуальной (лучше включить, чем исключить)
            return False, ""

        return False, ""
