from typing import Any

from playwright.async_api import Page

from core.parsers.base import BaseParser


class GazprombankCreditProductsParser(BaseParser):
    """
    Парсер кредитных продуктов Газпромбанка для частных лиц.

    Наследуется от BaseParser и реализует специфичную логику парсинга
    страницы с кредитными продуктами Газпромбанка.
    """

    def __init__(
        self,
        headless: bool = True,
        **kwargs,
    ):
        """
        Инициализация парсера Газпромбанка кредитных продуктов.

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
        Парсинг страницы с кредитными продуктами Газпромбанка.

        Args:
            url: URL страницы для парсинга

        Returns:
            Словарь с извлеченными данными о кредитных продуктах
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
        await self.random_delay(0.5, 1.0)

        products = []

        # Блок: продукты (productListing)
        try:
            # Ожидание появления контейнера с продуктами
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
                # Нажимаем на кнопку "Показать еще" если она есть, чтобы загрузить скрытые продукты
                await self._load_hidden_products(page, product_listing)

                # Прокручиваем страницу полностью для загрузки всех элементов
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await self.random_delay(0.5, 1.0)
                    await page.wait_for_load_state("networkidle")
                except Exception:
                    pass

                # Извлекаем все продукты из блока
                product_cards = product_listing.locator(".product_listing_base_card-a65")
                product_count = await product_cards.count()

                for i in range(product_count):
                    try:
                        card = product_cards.nth(i)

                        # Прокручиваем к карточке для загрузки, если нужно
                        await card.scroll_into_view_if_needed()
                        await self.random_delay(0.1, 0.2)

                        # Проверяем, не является ли продукт архивным
                        is_archived, _ = await self._is_archived_product(card)
                        if is_archived:
                            continue

                        product_data = await self._extract_product_data(card)
                        if product_data.get("title"):
                            products.append(product_data)
                    except Exception:
                        continue
        except Exception:
            pass  # Если блока нет, продолжаем

        return products

    async def _load_hidden_products(self, page: Page, container: Any) -> None:
        """
        Нажатие на кнопку "Показать еще" для загрузки скрытых продуктов.

        Args:
            page: Страница Playwright
            container: Контейнер с продуктами
        """
        try:
            # Получаем текущее количество продуктов перед загрузкой
            initial_products = container.locator(".product_listing_base_card-a65")
            initial_count = await initial_products.count()

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
                    break  # Кнопка исчезла, все продукты загружены

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

                # Проверяем, появились ли новые продукты
                current_products = container.locator(".product_listing_base_card-a65")
                current_count = await current_products.count()

                # Если количество продуктов не изменилось, возможно все загружено
                if current_count == initial_count:
                    # Дополнительная проверка - ждем еще немного
                    await self.random_delay(1.0, 1.5)
                    current_products = container.locator(
                        ".product_listing_base_card-a65"
                    )
                    current_count = await current_products.count()
                    if current_count == initial_count:
                        break  # Количество не изменилось, выходим

                initial_count = current_count
                clicks += 1

        except Exception as e:
            # Игнорируем ошибки при загрузке скрытых продуктов
            print(f"Ошибка при загрузке скрытых продуктов: {e}")
            pass

    async def _extract_product_data(self, card_locator: Any) -> dict[str, Any]:
        """
        Извлечение данных из одной карточки кредитного продукта.

        Args:
            card_locator: Локатор карточки продукта

        Returns:
            Словарь с данными о продукте
        """
        product_data: dict[str, Any] = {}

        try:
            # Название продукта
            title_locator = card_locator.locator(
                ".product_listing_base_card_description__title-9b0"
            ).first
            if await title_locator.count() > 0:
                title = await title_locator.text_content()
                product_data["title"] = title.strip() if title else None
            else:
                # Альтернативный вариант - скрытый заголовок
                hidden_title_locator = card_locator.locator(
                    ".product_listing_base_card_description__hidden_title-9b0"
                ).first
                if await hidden_title_locator.count() > 0:
                    title = await hidden_title_locator.text_content()
                    product_data["title"] = title.strip() if title else None
        except Exception:
            product_data["title"] = None

        try:
            # Описание продукта (подзаголовок)
            description_locator = card_locator.locator(".typography__subtitle-b1b").first
            if await description_locator.count() > 0:
                description = await description_locator.text_content()
                product_data["subtitle"] = description.strip() if description else None
        except Exception:
            product_data["subtitle"] = None

        try:
            # Сумма (price) - берем из бенефита
            benefit_title_locator = card_locator.locator(
                ".product_listing_base_card_benefit__title-e82"
            ).first
            if await benefit_title_locator.count() > 0:
                price = await benefit_title_locator.text_content()
                product_data["price"] = price.strip() if price else None

                # Описание суммы/условия (term) - берем из описания бенефита
                benefit_desc_locator = card_locator.locator(
                    ".product_listing_base_card_benefit__desc-e82"
                ).first
                if await benefit_desc_locator.count() > 0:
                    term = await benefit_desc_locator.text_content()
                    product_data["term"] = term.strip() if term else None
        except Exception:
            product_data["price"] = None
            product_data["term"] = None

        try:
            # Ссылка на оформление продукта
            apply_link_locator = card_locator.locator(
                ".product_listing_base_card_actions-288 a.button_primary-8e6"
            ).first
            if await apply_link_locator.count() > 0:
                apply_link = await apply_link_locator.get_attribute("href")
                if apply_link:
                    if not apply_link.startswith("http"):
                        apply_link = f"https://www.gazprombank.ru{apply_link}"
                    product_data["link"] = apply_link
            else:
                # Если нет кнопки оформления, пробуем найти любую ссылку
                details_link_locator = card_locator.locator(
                    ".product_listing_base_card_actions-288 a.button_tertiary-8e6"
                ).first
                if await details_link_locator.count() > 0:
                    link = await details_link_locator.get_attribute("href")
                    if link:
                        if not link.startswith("http"):
                            link = f"https://www.gazprombank.ru{link}"
                        product_data["link"] = link
        except Exception:
            product_data["link"] = None

        return product_data

    async def _is_archived_product(self, card_locator: Any) -> tuple[bool, str]:
        """
        Проверка, является ли продукт архивным.

        Args:
            card_locator: Локатор карточки продукта

        Returns:
            Кортеж (True если продукт архивный, строка с отладочной информацией)
        """
        try:
            # Проверяем наличие слова "архив" в названии или тексте
            card_text = await card_locator.text_content()
            if card_text:
                card_text_lower = card_text.lower()
                archive_keywords = [
                    "архив",
                    "архивная",
                    "архивный",
                    "(архивная)",
                    "(архивный)",
                ]
                if any(keyword in card_text_lower for keyword in archive_keywords):
                    return True, ""

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

            # Ключевые слова для кнопок оформления
            order_keywords = [
                "оформить кредит",
                "оставить заявку",
                "оформить",
                "получить кредит",
            ]

            has_order_button = False

            # Проверяем найденные кнопки
            for btn_info in buttons_info:
                if btn_info.get("isPrimary"):
                    btn_text = btn_info.get("text", "").lower()
                    if any(keyword in btn_text for keyword in order_keywords):
                        has_order_button = True
                        break

            # Если НЕТ кнопки оформления - это может быть архивный продукт
            if not has_order_button:
                # Дополнительная проверка: наличие слова "архив" в тексте карточки уже проверено выше
                return False, ""  # Считаем актуальным (лучше включить, чем исключить)

        except Exception:
            # В случае ошибки считаем продукт актуальным (лучше включить, чем исключить)
            return False, ""

        return False, ""
