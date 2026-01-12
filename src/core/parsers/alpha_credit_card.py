from typing import Any

from playwright.async_api import Page

from core.parsers.base import BaseParser


class AlphaCreditCardParser(BaseParser):
    """
    Парсер кредитных карт Альфа-Банка для частных лиц.

    Наследуется от BaseParser и реализует специфичную логику парсинга
    страницы с кредитными картами Альфа-Банка.
    """

    def __init__(
        self,
        headless: bool = True,
        **kwargs,
    ):
        """
        Инициализация парсера Альфа-Банка кредитных карт.

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
        Парсинг страницы с кредитными картами Альфа-Банка.

        Args:
            url: URL страницы для парсинга

        Returns:
            Словарь с извлеченными данными о кредитных картах
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

        # Ожидание появления контейнера с картами
        await page.wait_for_selector(
            'div[data-widget-name="Layout"]', timeout=self._timeout_to_ms()
        )

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
        Извлечение данных о всех кредитных картах.

        Args:
            page: Страница Playwright

        Returns:
            Список словарей с данными о картах
        """
        await page.wait_for_selector(
            'div[data-widget-name="Layout"]', timeout=self._timeout_to_ms()
        )
        await self.random_delay(0.5, 1.0)

        # Ищем CatalogCard внутри Layout
        card_elements = page.locator(
            'div[data-widget-name="Layout"] div[data-widget-name="CatalogCard"]'
        )
        cards_count = await card_elements.count()

        if cards_count == 0:
            # Пробуем найти через Block
            block_elements = page.locator(
                'div[data-widget-name="Layout"] > div[data-widget-name="Block"]'
            )
            blocks_count = await block_elements.count()

            # Ищем CatalogCard внутри каждого Block
            for i in range(min(blocks_count, 10)):  # Проверяем первые 10
                try:
                    block = block_elements.nth(i)
                    catalog_card = block.locator('div[data-widget-name="CatalogCard"]')
                    if await catalog_card.count() > 0:
                        # Используем этот селектор
                        card_elements = page.locator(
                            'div[data-widget-name="Layout"] div[data-widget-name="CatalogCard"]'
                        )
                        cards_count = await card_elements.count()
                        break
                except Exception:
                    continue

        # Если все еще не нашли, пробуем найти div с primary кнопками
        if cards_count == 0:
            card_elements = page.locator(
                'div[data-widget-name="Layout"] div:has(button[class*="primary"])'
            )
            cards_count = await card_elements.count()

        if cards_count == 0:
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

            except Exception as e:
                # Пропускаем карточку при ошибке, но продолжаем парсинг
                print(f"Ошибка при извлечении карты {i}: {e}")
                continue

        return cards

    async def _extract_card_data(self, card_locator: Any) -> dict[str, Any]:
        """
        Извлечение данных из одной карточки кредитной карты.

        Args:
            card_locator: Локатор карточки

        Returns:
            Словарь с данными о карте
        """
        card_data: dict[str, Any] = {}

        try:
            # Название карты
            # Ищем h2 с ссылкой внутри
            title_locator = card_locator.locator(
                "h2 > span > a.aXYDeT.gXYDeT.cXYDeT"
            ).first
            if await title_locator.count() > 0:
                title = await title_locator.text_content()
                card_data["title"] = title.strip() if title else None
            else:
                # Альтернативный вариант - просто h2 с любыми классами
                title_locator_alt = card_locator.locator("h2").first
                if await title_locator_alt.count() > 0:
                    title = await title_locator_alt.text_content()
                    if title:
                        card_data["title"] = title.strip()
                    else:
                        # Пробуем найти текст в ссылке внутри h2
                        title_link = card_locator.locator("h2 a").first
                        if await title_link.count() > 0:
                            title = await title_link.text_content()
                            card_data["title"] = title.strip() if title else None
        except Exception:
            card_data["title"] = None

        try:
            # Описание карты (первый параграф после заголовка)
            description_locator = card_locator.locator("p.aR7Oy1.nQWkTE.RQWkTE").first
            if await description_locator.count() > 0:
                description = await description_locator.text_content()
                card_data["description"] = description.strip() if description else None
        except Exception:
            card_data["description"] = None

        try:
            # Извлечение всех особенностей (кредитный лимит, кэшбэк и т.д.)
            # Блоки с особенностями находятся в div[data-test-id="grid"] с классом aUl5hC fUl5hC vQWkTE
            features_container = card_locator.locator(
                'div[data-test-id="grid"].aUl5hC.fUl5hC.vQWkTE'
            ).first
            features = []

            if await features_container.count() > 0:
                # Ищем все блоки с особенностями внутри контейнера
                # Каждая особенность в div.kUl5hC.lUl5hC с двумя параграфами
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
            # В Альфа-Банке бейджи могут быть в разных местах, но обычно их нет
            # Оставляем для совместимости со схемой
            card_data["badge"] = None
        except Exception:
            card_data["badge"] = None

        try:
            # Ссылка на оформление карты
            # Ищем кнопку "Оформить карту" внутри ссылки
            apply_link_locator = card_locator.locator(
                "a:has(button.button__primary)"
            ).first
            if await apply_link_locator.count() > 0:
                apply_link = await apply_link_locator.get_attribute("href")
                if apply_link:
                    if not apply_link.startswith("http"):
                        apply_link = f"https://alfabank.ru{apply_link}"
                    card_data["apply_link"] = apply_link
            else:
                # Альтернативный вариант - ищем button напрямую и его родительскую ссылку
                button_locator = card_locator.locator("button.button__primary").first
                if await button_locator.count() > 0:
                    parent_link = button_locator.locator("xpath=ancestor::a").first
                    if await parent_link.count() > 0:
                        apply_link = await parent_link.get_attribute("href")
                        if apply_link:
                            if not apply_link.startswith("http"):
                                apply_link = f"https://alfabank.ru{apply_link}"
                            card_data["apply_link"] = apply_link
        except Exception:
            card_data["apply_link"] = None

        try:
            # Ссылка на подробности о карте
            details_link_locator = card_locator.locator(
                'a.button__secondary:has-text("Подробнее")'
            ).first
            if await details_link_locator.count() > 0:
                details_link = await details_link_locator.get_attribute("href")
                if details_link:
                    if not details_link.startswith("http"):
                        # Проверяем, не внешняя ли ссылка
                        if not details_link.startswith(
                            "https://"
                        ) and not details_link.startswith("http://"):
                            details_link = f"https://alfabank.ru{details_link}"
                    card_data["details_link"] = details_link
        except Exception:
            card_data["details_link"] = None

        return card_data

    async def _is_archived_card(self, card_locator: Any) -> tuple[bool, str]:
        """
        Проверка, является ли карта архивной.

        Архивные карты не имеют кнопок "Оформить карту".
        Если таких кнопок нет - карта архивная.

        Args:
            card_locator: Локатор карточки

        Returns:
            Кортеж (True если карта архивная, строка с отладочной информацией)
        """
        try:
            # Ищем все кнопки и проверяем их через JavaScript
            # Классы динамические (button__primary_19w6u), поэтому используем JS для точной проверки
            buttons_info = await card_locator.evaluate("""
                (element) => {
                    const buttons = element.querySelectorAll('button');
                    const result = [];
                    for (let btn of buttons) {
                        const className = btn.className || '';
                        const isPrimary = className.includes('primary') && !className.includes('secondary');
                        if (isPrimary) {
                            // Получаем текст кнопки
                            const textP = btn.querySelector('p[data-test-id="text"]');
                            let text = '';
                            if (textP) {
                                text = textP.textContent || '';
                            } else {
                                const anyP = btn.querySelector('p');
                                text = anyP ? (anyP.textContent || '') : (btn.innerText || btn.textContent || '');
                            }
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
                "оформить карту",
                "заказать карту",
                "получить карту",
                "оформить",
                "заказать",
                "получить",
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

            # Если НЕТ кнопки "Оформить" - это архивная карта
            if not has_order_button:
                return True, ""

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
