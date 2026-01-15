import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any, Literal

from fake_useragent import UserAgent
from playwright.async_api import (
    Browser,
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)
from playwright_stealth import Stealth


class BaseParser(ABC):
    """
    Базовый класс парсера с инкапсуляцией логики работы с Playwright.

    Включает:
    - Автоматическую инициализацию и закрытие браузера
    - Скрытие автоматизации (stealth mode) через playwright-stealth
    - Использование случайных user agents
    - Управление контекстом браузера
    """

    DEFAULT_TIMEOUT = 30.0
    DEFAULT_VIEWPORT_WIDTH = 1920
    DEFAULT_VIEWPORT_HEIGHT = 1080
    DEFAULT_LOCALE = "ru-RU"
    DEFAULT_TIMEZONE = "Europe/Moscow"

    def __init__(
        self,
        browser_type: Literal["chromium", "firefox", "webkit"] = "chromium",
        headless: bool = True,
        viewport_width: int = DEFAULT_VIEWPORT_WIDTH,
        viewport_height: int = DEFAULT_VIEWPORT_HEIGHT,
        user_agent: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        locale: str = DEFAULT_LOCALE,
        timezone_id: str = DEFAULT_TIMEZONE,
        navigator_languages: tuple[str, ...] | None = None,
    ):
        """
        Инициализация базового парсера.

        Args:
            browser_type: Тип браузера (chromium, firefox, webkit)
            headless: Запуск в headless режиме
            viewport_width: Ширина viewport
            viewport_height: Высота viewport
            user_agent: Кастомный user agent (если None, будет использован случайный)
            timeout: Таймаут для операций в секундах
            locale: Локаль браузера
            timezone_id: Часовой пояс
            navigator_languages: Переопределение navigator.languages
                (если None, используется на основе locale)
        """

        self.browser_type_name = browser_type
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.user_agent = user_agent
        self.timeout = timeout
        self.locale = locale
        self.timezone_id = timezone_id

        # Настройка языков для stealth
        if navigator_languages is None:
            # Автоматическое определение на основе locale
            if locale.startswith("ru"):
                navigator_languages = ("ru-RU", "ru", "en-US", "en")
            elif locale.startswith("en"):
                navigator_languages = ("en-US", "en", "ru-RU", "ru")
            else:
                navigator_languages = (locale, locale.split("-")[0], "en-US", "en")
        self.navigator_languages = navigator_languages

        # Инициализация fake-useragent
        self.ua = UserAgent(
            browsers=["Google", "Chrome", "Firefox", "Edge"],
            os=["Windows"],
            platforms=["desktop"],
        )

        # Инициализация playwright-stealth с максимальными настройками
        self._stealth = Stealth(
            navigator_languages_override=self.navigator_languages,
        )

        # Внутренние переменные
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def _get_user_agent(self) -> str:
        return self.user_agent or self.ua.random

    def _timeout_to_ms(self, timeout: float | None = None) -> int:
        timeout_value = timeout or self.timeout
        if timeout_value < 0:
            raise ValueError("timeout cannot be negative")
        return int(timeout_value * 1000)

    async def _create_browser_context(self, browser: Browser, ua: str) -> BrowserContext:
        context = await browser.new_context(
            viewport={
                "width": self.viewport_width,
                "height": self.viewport_height,
            },
            user_agent=ua,
            locale=self.locale,
            timezone_id=self.timezone_id,
            permissions=[],
            ignore_https_errors=True,
            bypass_csp=True,
            extra_http_headers={
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,image/apng,*/*;q=0.8"
                ),
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            },
            has_touch=False,
            device_scale_factor=1,
            geolocation=None,
            color_scheme="light",
            reduced_motion="no-preference",
            forced_colors="none",
            screen={
                "width": self.viewport_width,
                "height": self.viewport_height,
            },
        )
        return context

    async def start(self) -> None:
        """Инициализировать браузер и создать контекст."""
        if self._playwright is not None:
            return

        self._playwright = await async_playwright().start()

        # Получить тип браузера
        browser_type: BrowserType = getattr(self._playwright, self.browser_type_name)

        # Запустить браузер с настройками для скрытия автоматизации
        self._browser = await browser_type.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
                "--disable-features=BlockInsecurePrivateNetworkRequests",
                # Скрытие автоматизации
                "--exclude-switches=enable-automation",
                "--disable-infobars",
                # Дополнительные флаги для реалистичности
                "--lang=ru-RU",
            ],
        )

        # Создать контекст с user agent
        user_agent = self._get_user_agent()
        self._context = await self._create_browser_context(self._browser, user_agent)

        # Применить playwright-stealth к контексту
        # Это автоматически применит все эвазии ко всем страницам в этом контексте
        await self._stealth.apply_stealth_async(self._context)

        # Создать страницу (stealth уже применен к контексту)
        self._page = await self._context.new_page()
        # Конвертируем секунды в миллисекунды для Playwright API
        self._page.set_default_timeout(self._timeout_to_ms(self.timeout))

    async def close(self) -> None:
        """Закрыть браузер и освободить ресурсы."""
        try:
            if self._page:
                await self._page.close()
                self._page = None
        except Exception:
            pass

        try:
            if self._context:
                await self._context.close()
                self._context = None
        except Exception:
            pass

        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
        except Exception:
            pass

        try:
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        except Exception:
            pass
        
        # Небольшая задержка для завершения всех внутренних задач Playwright
        await asyncio.sleep(0.1)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @property
    def page(self) -> Page:
        """
        Получить текущую страницу.

        Returns:
            Страница Playwright

        Raises:
            RuntimeError: Если браузер не инициализирован
        """
        if self._page is None:
            raise RuntimeError("Browser not initialized.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        """
        Получить текущий контекст браузера.

        Returns:
            Контекст браузера

        Raises:
            RuntimeError: Если браузер не инициализирован
        """
        if self._context is None:
            raise RuntimeError("Browser not initialized.")
        return self._context

    @property
    def browser(self) -> Browser:
        """
        Получить экземпляр браузера.

        Returns:
            Браузер Playwright

        Raises:
            RuntimeError: Если браузер не инициализирован
        """
        if self._browser is None:
            raise RuntimeError("Browser not initialized.")
        return self._browser

    async def new_page(self) -> Page:
        """
        Создать новую страницу в текущем контексте.

        Returns:
            Новая страница
        """
        if self._context is None:
            raise RuntimeError("Browser not initialized.")

        # Stealth уже применен к контексту, поэтому все новые страницы автоматически защищены
        page = await self._context.new_page()
        # Конвертируем секунды в миллисекунды для Playwright API
        page.set_default_timeout(self._timeout_to_ms(self.timeout))
        return page

    async def random_delay(self, min_delay: float = 0.5, max_delay: float = 2.0) -> None:
        """
        Случайная задержка для имитации человеческого поведения.

        Args:
            min_delay: Минимальная задержка в секундах
            max_delay: Максимальная задержка в секундах
        """
        await asyncio.sleep(random.uniform(min_delay, max_delay))

    async def human_like_scroll(self, page: Page, scroll_pause: float = 1.0) -> None:
        document_height = await page.evaluate("document.body.scrollHeight")

        if document_height <= 0:
            return

        viewport_height = self.viewport_height
        current_position = 0

        while current_position < document_height:
            scroll_amount = random.randint(viewport_height // 3, viewport_height // 2)
            current_position = min(current_position + scroll_amount, document_height)

            await page.evaluate("(position) => window.scrollTo(0, position)", current_position)
            await asyncio.sleep(scroll_pause + random.uniform(0, 0.5))

            if random.random() < 0.3:
                await asyncio.sleep(random.uniform(0.5, 2.0))

    @abstractmethod
    async def parse_page(self, url: str) -> dict[str, Any]:
        """
        Абстрактный метод для парсинга страницы.

        Должен быть реализован в наследниках для конкретной логики парсинга.

        Args:
            url: URL страницы для парсинга

        Returns:
            Словарь с извлеченными данными
        """
        pass

    async def wait_for_element(
        self,
        selector: str,
        timeout: float | None = None,
    ) -> None:
        """
        Ожидание появления элемента на странице.

        Args:
            selector: CSS селектор элемента
            timeout: Таймаут ожидания в секундах. Если None, используется self.timeout
        """
        page = self.page
        await page.wait_for_selector(selector, timeout=self._timeout_to_ms(timeout))

    async def click_and_wait(
        self,
        selector: str,
        wait_selector: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """
        Клик по элементу с ожиданием загрузки.

        Args:
            selector: CSS селектор элемента для клика
            wait_selector: Селектор элемента, появления которого нужно ждать
            timeout: Таймаут ожидания в секундах. Если None, используется timeout из конструктора
        """
        page = self.page

        await page.click(selector)
        await self.random_delay(0.5, 1.0)

        if wait_selector:
            await self.wait_for_element(wait_selector, timeout)
