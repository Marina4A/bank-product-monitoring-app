from typing import Any

from playwright.async_api import Page

from core.parsers.base import BaseParser


class GazprombankCreditCardParser(BaseParser):
    """
    Парсер кредитных карт Газпромбанка для частных лиц.

    Наследуется от BaseParser и реализует специфичную логику парсинга
    страницы с кредитными картами Газпромбанка.
    """

    def __init__(
        self,
        headless: bool = True,
        **kwargs,
    ):
        """
        Инициализация парсера Газпромбанка кредитных карт.

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
        Парсинг страницы с кредитными картами Газпромбанка.

        Args:
            url: URL страницы для парсинга

        Returns:
            Словарь с извлеченными данными о кредитных картах
        """
        page = self.page

        # Убеждаемся, что viewport десктопный
        await page.set_viewport_size({"width": 1920, "height": 1080})

        # Устанавливаем десктопный user agent через переопределение navigator
        desktop_ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )

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

        # Ожидание networkidle с таймаутом, чтобы не зависнуть навсегда
        try:
            await page.wait_for_load_state(
                "networkidle", timeout=self._timeout_to_ms(10.0)
            )
        except Exception:
            # Если networkidle не достигнут, продолжаем - это нормально для SPA
            pass

        # Имитация человеческого поведения
        await self.random_delay(1.0, 2.0)

        # Прокрутка страницы для загрузки lazy-loaded элементов
        try:
            # Прокручиваем по частям, имитируя человеческое поведение
            scroll_height = await page.evaluate(
                "document.body.scrollHeight || document.documentElement.scrollHeight"
            )
            if scroll_height > 0:
                # Прокручиваем до середины
                await page.evaluate(f"window.scrollTo(0, {scroll_height} / 2)")
                await self.random_delay(0.5, 1.0)
                # Ждем загрузки контента
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=self._timeout_to_ms(5.0)
                    )
                except Exception:
                    pass
                # Прокручиваем до конца
                await page.evaluate(f"window.scrollTo(0, {scroll_height})")
                await self.random_delay(0.5, 1.0)
                # Ждем загрузки контента
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=self._timeout_to_ms(5.0)
                    )
                except Exception:
                    pass
                # Возвращаемся наверх для начала парсинга
                await page.evaluate("window.scrollTo(0, 0)")
                await self.random_delay(0.5, 1.0)
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
        await self.random_delay(0.5, 1.0)

        cards = []

        # Первый блок: выбранная карта (chosen_listing_product_collection)
        try:
            # Ожидание появления контейнера с таймаутом
            try:
                await page.wait_for_selector(
                    '[data-code="chosen_listing_product_collection"]',
                    timeout=self._timeout_to_ms(5.0),
                    state="attached",
                )
            except Exception:
                pass  # Если контейнер не появился, продолжаем

            chosen_cards_container = page.locator(
                '[data-code="chosen_listing_product_collection"]'
            ).first
            if await chosen_cards_container.count() > 0:
                chosen_cards = chosen_cards_container.locator(
                    ".product_listing_base_card-a65"
                )
                chosen_count = await chosen_cards.count()

                for i in range(chosen_count):
                    try:
                        card = chosen_cards.nth(i)
                        await card.scroll_into_view_if_needed()
                        card_data = await self._extract_card_data(card)
                        if card_data.get("title"):
                            cards.append(card_data)
                    except Exception:
                        continue
        except Exception:
            pass  # Если первого блока нет, продолжаем

        # Второй блок: остальные карты (productListing)
        try:
            # Ожидание появления контейнера с остальными картами
            try:
                await page.wait_for_selector(
                    '[data-code="productListing"]',
                    timeout=self._timeout_to_ms(5.0),
                    state="attached",
                )
            except Exception:
                pass  # Если контейнер не появился, продолжаем

            product_listing = page.locator('[data-code="productListing"]').first
            if await product_listing.count() > 0:
                # Нажимаем на кнопку "Показать еще" если она есть, чтобы загрузить скрытые карты
                await self._load_hidden_cards(page, product_listing)

                # Прокручиваем страницу полностью для загрузки всех элементов
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await self.random_delay(0.5, 1.0)
                    await page.wait_for_load_state("networkidle")
                except Exception:
                    pass

                # Извлекаем все карты из второго блока
                product_cards = product_listing.locator(".product_listing_base_card-a65")
                product_count = await product_cards.count()

                for i in range(product_count):
                    try:
                        card = product_cards.nth(i)

                        # Прокручиваем к карточке для загрузки, если нужно
                        await card.scroll_into_view_if_needed()
                        await self.random_delay(0.1, 0.2)

                        # Проверяем, не является ли карта архивной
                        is_archived, _ = await self._is_archived_card(card)
                        if is_archived:
                            continue

                        card_data = await self._extract_card_data(card)
                        if card_data.get("title"):
                            cards.append(card_data)
                    except Exception:
                        continue
        except Exception:
            pass  # Если второго блока нет, продолжаем

        return cards

    async def _load_hidden_cards(self, page: Page, container: Any) -> None:
        """
        Нажатие на кнопку "Показать еще" для загрузки скрытых карт.

        Args:
            page: Страница Playwright
            container: Контейнер с картами
        """
        try:
            # Получаем текущее количество карт перед загрузкой
            initial_cards = container.locator(".product_listing_base_card-a65")
            initial_count = await initial_cards.count()

            # Может быть несколько нажатий, повторяем пока кнопка есть
            max_clicks = 10  # Ограничиваем количество попыток
            clicks = 0

            while clicks < max_clicks:
                # Ищем кнопку "Показать еще" в контейнере
                show_more_button = container.locator(
                    ".product_listing_base__show_more-65d button"
                ).first

                # Проверяем наличие и видимость кнопки
                if await show_more_button.count() == 0:
                    break  # Кнопка исчезла, все карты загружены

                # Проверяем, не скрыта ли кнопка
                try:
                    is_visible = await show_more_button.is_visible()
                    if not is_visible:
                        break
                except Exception:
                    break

                # Прокручиваем к кнопке перед кликом
                await show_more_button.scroll_into_view_if_needed()
                await self.random_delay(0.5, 1.0)

                # Нажимаем на кнопку
                await show_more_button.click()

                # Ожидание загрузки новых элементов после клика
                await self.random_delay(1.5, 2.5)
                await page.wait_for_load_state("networkidle")

                # Прокручиваем страницу, чтобы загрузить новые элементы в DOM
                # Это важно, так как некоторые элементы могут быть lazy-loaded
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await self.random_delay(0.5, 1.0)
                    # Возвращаемся немного вверх для стабильности
                    await page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight - 500)"
                    )
                    await self.random_delay(0.3, 0.5)
                except Exception:
                    pass

                # Ждем еще немного для полной загрузки
                await page.wait_for_load_state("networkidle")

                # Проверяем, появились ли новые карты
                current_cards = container.locator(".product_listing_base_card-a65")
                current_count = await current_cards.count()

                # Если количество карт не изменилось, возможно все загружено
                if current_count == initial_count:
                    # Дополнительная проверка - ждем еще немного
                    await self.random_delay(1.0, 1.5)
                    current_cards = container.locator(".product_listing_base_card-a65")
                    current_count = await current_cards.count()
                    if current_count == initial_count:
                        break  # Количество не изменилось, выходим

                initial_count = current_count
                clicks += 1

        except Exception as e:
            # Игнорируем ошибки при загрузке скрытых карт
            print(f"Ошибка при загрузке скрытых карт: {e}")
            pass

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
            title_locator = card_locator.locator(
                ".product_listing_base_card_description__title-9b0"
            ).first
            if await title_locator.count() > 0:
                title = await title_locator.text_content()
                card_data["title"] = title.strip() if title else None
            else:
                # Альтернативный вариант - скрытый заголовок
                hidden_title_locator = card_locator.locator(
                    ".product_listing_base_card_description__hidden_title-9b0"
                ).first
                if await hidden_title_locator.count() > 0:
                    title = await hidden_title_locator.text_content()
                    card_data["title"] = title.strip() if title else None
        except Exception:
            card_data["title"] = None

        try:
            # Описание карты (подзаголовок)
            description_locator = card_locator.locator(".typography__subtitle-b1b").first
            if await description_locator.count() > 0:
                description = await description_locator.text_content()
                card_data["description"] = description.strip() if description else None
        except Exception:
            card_data["description"] = None

        try:
            # Извлечение бенефита (особенность карты)
            benefit_container = card_locator.locator(
                ".product_listing_base_card_benefit-e82"
            ).first
            features = []

            if await benefit_container.count() > 0:
                # Заголовок бенефита (value)
                benefit_title_locator = benefit_container.locator(
                    ".product_listing_base_card_benefit__title-e82"
                ).first
                # Описание бенефита (label)
                benefit_desc_locator = benefit_container.locator(
                    ".product_listing_base_card_benefit__desc-e82"
                ).first

                if await benefit_title_locator.count() > 0:
                    value = await benefit_title_locator.text_content()
                    label = (
                        await benefit_desc_locator.text_content()
                        if await benefit_desc_locator.count() > 0
                        else None
                    )

                    if value:
                        features.append(
                            {
                                "value": value.strip(),
                                "label": label.strip() if label else "",
                            }
                        )

            card_data["features"] = features if features else None
        except Exception:
            card_data["features"] = None

        try:
            # Бейдж (теги) - может быть несколько тегов
            tags_container = card_locator.locator(
                ".product_listing_base_card__tags-a65"
            ).first
            if await tags_container.count() > 0:
                tags = tags_container.locator(".tag-d76")
                tags_count = await tags.count()
                badges = []

                for i in range(tags_count):
                    try:
                        tag = tags.nth(i)
                        tag_text = await tag.text_content()
                        if tag_text:
                            badges.append(tag_text.strip())
                    except Exception:
                        continue

                card_data["badge"] = ", ".join(badges) if badges else None
            else:
                card_data["badge"] = None
        except Exception:
            card_data["badge"] = None

        try:
            # Ссылка на оформление карты
            apply_link_locator = card_locator.locator(
                ".product_listing_base_card_actions-288 a.button_primary-8e6"
            ).first
            if await apply_link_locator.count() > 0:
                apply_link = await apply_link_locator.get_attribute("href")
                if apply_link:
                    if not apply_link.startswith("http"):
                        apply_link = f"https://www.gazprombank.ru{apply_link}"
                    card_data["apply_link"] = apply_link
        except Exception:
            card_data["apply_link"] = None

        try:
            # Ссылка на подробности о карте
            details_link_locator = card_locator.locator(
                ".product_listing_base_card_actions-288 a.button_tertiary-8e6"
            ).first
            if await details_link_locator.count() > 0:
                details_link = await details_link_locator.get_attribute("href")
                if details_link:
                    if not details_link.startswith("http"):
                        details_link = f"https://www.gazprombank.ru{details_link}"
                    card_data["details_link"] = details_link
            else:
                # Иногда может быть только одна ссылка "Подробнее"
                details_link_locator_alt = card_locator.locator(
                    '.product_listing_base_card_actions-288 a:has-text("Подробнее")'
                ).first
                if await details_link_locator_alt.count() > 0:
                    details_link = await details_link_locator_alt.get_attribute("href")
                    if details_link:
                        if not details_link.startswith("http"):
                            details_link = f"https://www.gazprombank.ru{details_link}"
                        card_data["details_link"] = details_link
        except Exception:
            card_data["details_link"] = None

        return card_data

    async def _is_archived_card(self, card_locator: Any) -> tuple[bool, str]:
        """
        Проверка, является ли карта архивной.

        Args:
            card_locator: Локатор карточки

        Returns:
            Кортеж (True если карта архивная, строка с отладочной информацией)
        """
        try:
            # Проверяем наличие кнопок оформления
            buttons_info = await card_locator.evaluate("""
                (element) => {
                    const buttons = element.querySelectorAll('a[class*="button"], button');
                    const result = [];
                    for (let btn of buttons) {
                        const className = btn.className || '';
                        const text = btn.innerText || btn.textContent || '';
                        const isPrimary = className.includes('primary') ||
                                         className.includes('button_primary');
                        result.push({
                            isPrimary: isPrimary,
                            text: text.trim(),
                            className: className
                        });
                    }
                    return result;
                }
            """)

            # Ключевые слова для кнопок заказа
            order_keywords = [
                "оформить карту",
                "оформить",
                "о карте",
                "получить карту",
                "заказать карту",
            ]

            has_order_button = False

            # Проверяем найденные кнопки
            for btn_info in buttons_info:
                if btn_info.get("isPrimary"):
                    btn_text = btn_info.get("text", "").lower()
                    if any(keyword in btn_text for keyword in order_keywords):
                        has_order_button = True
                        break

            # Если НЕТ кнопки "Оформить" и есть только "Подробнее" - это может быть архивная карта
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

                # Если нет кнопки оформления и нет явных признаков архива,
                # но есть только кнопка "Подробнее" - считаем актуальной
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
