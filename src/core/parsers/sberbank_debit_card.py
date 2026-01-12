"""
Парсер дебетовых карт Сбербанка на основе Selenium.

Использует Firefox браузер, где уже установлены все необходимые сертификаты Минцифры.
Это решает проблему с сертификатами, так как Selenium использует реальный
установленный браузер со всеми его настройками.

ВАЖНО: Перед использованием парсера:
1. Убедитесь, что Firefox установлен и в нем установлены сертификаты Минцифры
   - Откройте Firefox вручную
   - Перейдите на https://www.sberbank.ru
   - Если появится ошибка сертификата, установите сертификаты Минцифры
   - Инструкции: https://www.gosuslugi.ru/crt
2. ЗАКРОЙТЕ ВСЕ ОКНА FIREFOX перед запуском парсера (профиль не должен быть заблокирован)
   - Закройте все вкладки Firefox
   - Закройте все фоновые процессы Firefox
   - Проверьте диспетчер задач (Ctrl+Shift+Esc) - не должно быть процессов firefox.exe
3. Установите зависимости: pip install selenium webdriver-manager
   Или используйте: uv sync (если используете uv)

Если Firefox открыт, парсер попытается использовать системные сертификаты Windows,
но для гарантированной работы с сертификатами Минцифры лучше закрыть Firefox.

Использование:
    async with SberbankDebitCardSeleniumParser(headless=False) as parser:
        data = await parser.parse_page("https://www.sberbank.ru/ru/person/bank_cards/debit")
"""

import asyncio
import os
import random
from pathlib import Path
from typing import Any
import traceback

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webdriver import WebDriver
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
import shutil

class SberbankDebitCardSeleniumParser:
    """
    Парсер дебетовых карт Сбербанка на основе Selenium.

    Автоматически определяет доступный браузер (Chrome или Firefox) и использует его
    для парсинга. Приоритет: Chrome → Firefox. Это позволяет обойти проблему с сертификатами
    при использовании Playwright.

    Особенности:
    - Автоматический выбор браузера (Chrome приоритетен, затем Firefox)
    - Использует реальный браузер со всеми установленными сертификатами
    - Обрабатывает динамически загружаемые карты (кнопка "Показать больше")
    - Парсит карты из нескольких блоков на странице
    - Автоматический fallback: если Chrome не удалось запустить, использует Firefox
    """

    DEFAULT_TIMEOUT = 30.0
    DEFAULT_VIEWPORT_WIDTH = 1920
    DEFAULT_VIEWPORT_HEIGHT = 1080

    def __init__(
        self,
        headless: bool = True,
        chrome_profile_path: str | None = None,
        viewport_width: int = DEFAULT_VIEWPORT_WIDTH,
        viewport_height: int = DEFAULT_VIEWPORT_HEIGHT,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Инициализация парсера на основе Selenium.

        Args:
            headless: Запуск в headless режиме
            chrome_profile_path: Путь к профилю Firefox (оставлено для совместимости, не используется)
            viewport_width: Ширина окна браузера
            viewport_height: Высота окна браузера
            timeout: Таймаут для операций в секундах
        """
        self.headless = headless
        self.chrome_profile_path = chrome_profile_path  # Оставлено для совместимости
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.timeout = timeout
        self._driver: WebDriver | None = None

    def _check_browser_installed(self, browser_name: str) -> bool:
        """
        Проверить, установлен ли браузер в системе.

        Args:
            browser_name: Имя браузера ('chrome' или 'firefox')

        Returns:
            True, если браузер установлен, False в противном случае
        """
        if browser_name.lower() == 'chrome':
            # Проверяем наличие Chrome через shutil.which
            chrome_path = shutil.which('chrome') or shutil.which('google-chrome') or shutil.which('chromium')
            if chrome_path:
                return True

            # Дополнительная проверка для Windows
            if os.name == 'nt':
                chrome_paths = [
                    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                    Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
                    Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
                ]
                for path in chrome_paths:
                    if path.exists():
                        return True

        elif browser_name.lower() == 'firefox':
            # Проверяем наличие Firefox через shutil.which
            firefox_path = shutil.which('firefox') or shutil.which('mozilla-firefox')
            if firefox_path:
                return True

            # Дополнительная проверка для Windows
            if os.name == 'nt':
                firefox_paths = [
                    Path("C:/Program Files/Mozilla Firefox/firefox.exe"),
                    Path("C:/Program Files (x86)/Mozilla Firefox/firefox.exe"),
                    Path.home() / "AppData/Local/Mozilla Firefox/firefox.exe",
                ]
                for path in firefox_paths:
                    if path.exists():
                        return True

        return False

    def _get_available_browser(self) -> str | None:
        """
        Определить доступный браузер с приоритетом: Chrome → Firefox.

        Returns:
            'chrome', 'firefox' или None, если ни один не найден
        """
        if self._check_browser_installed('chrome'):
            return 'chrome'
        elif self._check_browser_installed('firefox'):
            return 'firefox'
        return None

    def _get_firefox_profile_path(self) -> str | None:
        """
        Получить путь к профилю Firefox пользователя.

        Returns:
            Путь к профилю Firefox или None, если не найден
        """
        if os.name == 'nt':  # Windows
            # Firefox хранит профили в разных местах, в зависимости от версии
            # Обычно: %APPDATA%\Mozilla\Firefox\Profiles\
            firefox_profiles = Path.home() / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles"
            if firefox_profiles.exists():
                # Ищем профиль по умолчанию (обычно заканчивается на .default или .default-release)
                for profile_dir in firefox_profiles.iterdir():
                    if profile_dir.is_dir() and (profile_dir.name.endswith('.default') or
                                                  profile_dir.name.endswith('.default-release')):
                        return str(profile_dir)
        return None

    def _create_chrome_driver(self) -> WebDriver:
        """
        Создать драйвер Chrome, используя системные сертификаты Windows.

        Returns:
            Экземпляр WebDriver для Chrome
        """
        chrome_options = ChromeOptions()

        # Базовые настройки
        if self.headless:
            chrome_options.add_argument("--headless=new")

        chrome_options.add_argument(f"--window-size={self.viewport_width},{self.viewport_height}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--lang=ru-RU")
        chrome_options.add_argument("--start-maximized")

        # Устанавливаем user agent
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

        # Скрываем признаки автоматизации
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # Полагаемся на системные сертификаты Windows
        chrome_options.add_argument("--allow-running-insecure-content")
        # Игнорируем ошибки сертификата
        chrome_options.add_argument("--ignore-certificate-errors")

        print("Используется Chrome с системными сертификатами Windows и игнорированием ошибок сертификата")

        try:
            # Используем webdriver-manager для автоматической установки драйвера
            service = ChromeService(ChromeDriverManager().install())

            # Создаем драйвер Chrome
            driver = webdriver.Chrome(service=service, options=chrome_options)

            # Скрываем признаки автоматизации через JavaScript
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'platform', {
                        get: () => 'Win32'
                    });
                '''
            })

            return driver
        except Exception as e:
            print(f"\nОшибка при создании драйвера Chrome: {e}\n")
            raise

    def _create_firefox_driver(self) -> WebDriver:
        """
        Создать драйвер Firefox, используя системные сертификаты Windows.

        Returns:
            Экземпляр WebDriver для Firefox
        """
        firefox_options = FirefoxOptions()

        # Базовые настройки
        if self.headless:
            firefox_options.add_argument("--headless")

        firefox_options.set_preference("general.useragent.override",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0")

        # Настройки окна
        firefox_options.set_preference("width", self.viewport_width)
        firefox_options.set_preference("height", self.viewport_height)

        # Язык интерфейса
        firefox_options.set_preference("intl.accept_languages", "ru-RU,ru,en-US,en")

        # Скрываем признаки автоматизации
        firefox_options.set_preference("dom.webdriver.enabled", False)
        firefox_options.set_preference("useAutomationExtension", False)

        # Работа с сертификатами
        # Полагаемся на системные сертификаты Windows
        firefox_options.set_preference("security.tls.insecure_fallback_hosts", "sberbank.ru,www.sberbank.ru")
        firefox_options.set_preference("security.tls.unrestricted_rc4_fallback", True)
        # Используем системные сертификаты Windows
        firefox_options.set_preference("security.enterprise_roots.enabled", True)

        print("Используется Firefox с системными сертификатами Windows")

        try:
            # Используем webdriver-manager для автоматической установки драйвера
            service = FirefoxService(GeckoDriverManager().install())

            # Создаем драйвер Firefox
            driver = webdriver.Firefox(service=service, options=firefox_options)

            # Настраиваем размер окна
            driver.set_window_size(self.viewport_width, self.viewport_height)

            # Скрываем признаки автоматизации через JavaScript
            # Firefox не поддерживает CDP, используем execute_script
            driver.execute_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32'
                });
            """)

            return driver
        except Exception as e:
            print(f"\nОшибка при создании драйвера Firefox: {e}\n")
            raise

    def _create_driver(self) -> WebDriver:
        """
        Создать драйвер браузера с автоматическим выбором: Chrome (приоритет) → Firefox.

        Returns:
            Экземпляр WebDriver
        """
        # Определяем доступный браузер
        browser = self._get_available_browser()

        if browser is None:
            raise RuntimeError(
                "Не найден ни один из поддерживаемых браузеров (Chrome или Firefox).\n"
                "Пожалуйста, установите Chrome или Firefox для использования парсера."
            )

        # Пытаемся создать драйвер для выбранного браузера
        if browser == 'chrome':
            try:
                return self._create_chrome_driver()
            except Exception as chrome_error:
                print(f"\nНе удалось создать драйвер Chrome: {chrome_error}")
                print("Пробую использовать Firefox в качестве запасного варианта...")
                # Если Chrome не удалось запустить, пробуем Firefox
                if self._check_browser_installed('firefox'):
                    try:
                        return self._create_firefox_driver()
                    except Exception as firefox_error:
                        print(f"\nНе удалось создать драйвер Firefox: {firefox_error}")
                        raise RuntimeError(
                            f"Не удалось создать драйвер ни для Chrome, ни для Firefox.\n"
                            f"Ошибки: Chrome - {chrome_error}, Firefox - {firefox_error}"
                        )
                else:
                    raise RuntimeError(
                        f"Не удалось создать драйвер Chrome, а Firefox не установлен.\n"
                        f"Ошибка Chrome: {chrome_error}"
                    )

        elif browser == 'firefox':
            try:
                return self._create_firefox_driver()
            except Exception as firefox_error:
                raise RuntimeError(
                    f"Не удалось создать драйвер Firefox.\n"
                    f"Ошибка: {firefox_error}"
                )

        # Не должно быть достигнуто, но на всякий случай
        raise RuntimeError(f"Неподдерживаемый браузер: {browser}")

    async def start(self) -> None:
        """Инициализировать браузер."""
        if self._driver is None:
            # Selenium не поддерживает async напрямую, поэтому используем executor
            loop = asyncio.get_event_loop()
            self._driver = await loop.run_in_executor(None, self._create_driver)

    async def close(self) -> None:
        """Закрыть браузер и освободить ресурсы."""
        if self._driver:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._driver.quit)
            self._driver = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @property
    def driver(self) -> WebDriver:
        """Получить текущий драйвер."""
        if self._driver is None:
            raise RuntimeError("Driver not initialized. Call start() first.")
        return self._driver

    async def random_delay(self, min_delay: float = 0.5, max_delay: float = 2.0) -> None:
        """Случайная задержка для имитации человеческого поведения."""
        await asyncio.sleep(random.uniform(min_delay, max_delay))

    async def parse_page(self, url: str) -> dict[str, Any]:
        """
        Парсинг страницы с дебетовыми картами Сбербанка.

        Args:
            url: URL страницы для парсинга

        Returns:
            Словарь с извлеченными данными о дебетовых картах
        """
        driver = self.driver

        # Переход на страницу
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, driver.get, url)

        # Увеличиваем время ожидания для полной загрузки страницы
        await self.random_delay(2.0, 3.0)

        # Ожидание загрузки страницы и появления элементов
        wait = WebDriverWait(driver, self.timeout)

        # Ждем появления хотя бы одного текстового виджета или контента
        try:
            # Проверяем загрузку через JavaScript
            page_ready = await loop.run_in_executor(
                None,
                driver.execute_script,
                """
                // Ждем загрузки DOM и появления элементов
                const checkReady = () => {
                    const widgets = document.querySelectorAll('[data-test-id="ZeroBlockTextWidget"]');
                    const hasContent = document.body.textContent.includes('СберКарта') ||
                                      document.body.textContent.includes('Платёжный');
                    return widgets.length > 0 || hasContent;
                };

                // Ждем до 10 секунд
                const startTime = Date.now();
                const maxWait = 10000;
                while (Date.now() - startTime < maxWait) {
                    if (document.readyState === 'complete' && checkReady()) {
                        return true;
                    }
                    // Небольшая задержка
                    const start = Date.now();
                    while (Date.now() - start < 100) {}
                }
                return checkReady();
                """
            )
            if page_ready:
                print("Страница загружена, элементы найдены")
            else:
                print("Страница может быть не полностью загружена, продолжаем парсинг...")
        except Exception as e:
            print(f"Ошибка при проверке загрузки страницы: {e}, продолжаем парсинг...")

        # Проверяем, не появилась ли страница с ошибкой сертификата
        try:
            # page_source - это свойство, а не метод
            page_source = await loop.run_in_executor(None, lambda: driver.page_source)
            if "Возникла проблема при открытии сайта Сбербанка" in page_source or \
               "не установлены сертификаты Национального УЦ Минцифры" in page_source:
                raise Exception(
                    "Обнаружена страница с ошибкой сертификатов. "
                    "Убедитесь, что сертификаты Минцифры установлены в Firefox."
                )
        except Exception as e:
            # Если ошибка при проверке, пробуем продолжить
            if "сертификатов" not in str(e).lower():
                print(f"Предупреждение при проверке страницы: {e}")
            pass

        # Прокрутка для загрузки lazy-loaded элементов (несколько раз)
        try:
            # Прокручиваем постепенно для загрузки всего контента
            for scroll_step in [0.25, 0.5, 0.75, 1.0]:
                await loop.run_in_executor(
                    None,
                    driver.execute_script,
                    f"window.scrollTo(0, document.body.scrollHeight * {scroll_step});"
                )
                await self.random_delay(0.3, 0.5)
        except Exception:
            pass

        # Извлечение данных о всех картах
        cards = await self._extract_cards(driver)

        # Отладочный вывод
        print(f"Извлечено карт: {len(cards)}")
        if len(cards) == 0:
            # Попробуем найти хотя бы одну карту простым способом
            print("Универсальный метод не нашел карты. Попытка альтернативного извлечения данных...")
            debug_info = await loop.run_in_executor(
                None,
                driver.execute_script,
                """
                const info = {
                    totalTextWidgets: document.querySelectorAll('[data-test-id="ZeroBlockTextWidget"]').length,
                    hasSberkarta: document.body.textContent.includes('СберКарта'),
                    hasPlatSticker: document.body.textContent.includes('Платёжный стикер'),
                    hasMolodejnaya: document.body.textContent.includes('Молодёжная'),
                    hasDetskaya: document.body.textContent.includes('Детская'),
                    hasBlock2: !!document.querySelector('[data-test-id="ZeroBlock2"]'),
                    sampleTexts: []
                };

                // Берем первые 20 текстовых виджетов для отладки
                const widgets = document.querySelectorAll('[data-test-id="ZeroBlockTextWidget"]');
                for (let i = 0; i < Math.min(20, widgets.length); i++) {
                    const text = (widgets[i].textContent || '').trim();
                    if (text && text.length > 0 && text.length < 300) {
                        info.sampleTexts.push(text);
                    }
                }

                return info;
                """
            )
            print(f"Отладочная информация:")
            print(f"  Всего виджетов с текстом: {debug_info.get('totalTextWidgets', 0)}")
            print(f"  Есть 'СберКарта': {debug_info.get('hasSberkarta', False)}")
            print(f"  Есть 'Платёжный стикер': {debug_info.get('hasPlatSticker', False)}")
            print(f"  Есть 'Молодёжная': {debug_info.get('hasMolodejnaya', False)}")
            print(f"  Есть 'Детская': {debug_info.get('hasDetskaya', False)}")
            print(f"  Есть блок 'ZeroBlock2': {debug_info.get('hasBlock2', False)}")
            print(f"  Примеры текстов (первые 5):")
            for i, text in enumerate(debug_info.get('sampleTexts', [])[:5], 1):
                print(f"    {i}. {text[:100]}{'...' if len(text) > 100 else ''}")

        # Получаем title правильно (это свойство, а не метод)
        title = await loop.run_in_executor(None, lambda: driver.title)

        return {
            "url": url,
            "title": title,
            "cards_count": len(cards),
            "cards": cards,
        }

    async def _extract_cards(self, driver: WebDriver) -> list[dict[str, Any]]:
        """
        Извлечение данных о всех дебетовых картах.

        Args:
            driver: WebDriver экземпляр

        Returns:
            Список словарей с данными о картах
        """
        cards = []
        loop = asyncio.get_event_loop()

        # Используем универсальный подход: извлекаем все карты одним запросом
        try:
            all_cards_data = await self._extract_all_cards_universal(driver)
            if all_cards_data:
                cards.extend(all_cards_data)
                print(f"Универсальный метод нашел {len(all_cards_data)} карт")
        except Exception as e:
            print(f"Ошибка при универсальном парсинге: {e}")
            import traceback
            traceback.print_exc()

        # 1. Парсим первый блок с основными картами (СберКарта, Платёжный стикер)
        if len(cards) == 0:
            try:
                first_block_cards = await self._extract_first_block_cards(driver)
                cards.extend(first_block_cards)
                print(f"Первый блок: найдено {len(first_block_cards)} карт")
            except Exception as e:
                print(f"Ошибка при парсинге первого блока: {e}")

        # 2. Парсим второй блок "Другие дебетовые карты"
        try:
            second_block_cards = await self._extract_second_block_cards(driver)
            cards.extend(second_block_cards)
            print(f"Второй блок: найдено {len(second_block_cards)} карт")
        except Exception as e:
            print(f"Ошибка при парсинге второго блока: {e}")

        # 3. Пытаемся найти и нажать кнопку "Показать больше"
        try:
            show_more_selectors = [
                "//*[contains(text(), 'Показать больше')]",
                "//div[contains(text(), 'Показать больше')]",
                "//button[contains(text(), 'Показать больше')]",
                "//span[contains(text(), 'Показать больше')]",
            ]

            show_more_button = None
            for selector in show_more_selectors:
                try:
                    elements = await loop.run_in_executor(
                        None,
                        driver.find_elements,
                        By.XPATH,
                        selector
                    )
                    if elements:
                        # Проверяем видимость через JavaScript (более надежно)
                        is_visible = await loop.run_in_executor(
                            None,
                            driver.execute_script,
                            """
                            const el = arguments[0];
                            const rect = el.getBoundingClientRect();
                            const style = window.getComputedStyle(el);
                            return rect.width > 0 && rect.height > 0 &&
                                   style.display !== 'none' &&
                                   style.visibility !== 'hidden' &&
                                   style.opacity !== '0';
                            """,
                            elements[0]
                        )
                        if is_visible:
                            show_more_button = elements[0]
                            break
                except Exception:
                    continue

            if show_more_button:
                # Прокрутка к кнопке с использованием JavaScript
                await loop.run_in_executor(
                    None,
                    driver.execute_script,
                    """
                    arguments[0].scrollIntoView({
                        behavior: 'smooth',
                        block: 'center',
                        inline: 'nearest'
                    });
                    """,
                    show_more_button
                )
                await self.random_delay(0.8, 1.2)

                # Клик по кнопке через JavaScript (чтобы обойти проблему с перекрытием элементов)
                # Это более надежный способ, чем обычный клик
                try:
                    # Используем JavaScript клик напрямую, так как элемент может быть перекрыт
                    click_success = await loop.run_in_executor(
                        None,
                        driver.execute_script,
                        """
                        try {
                            arguments[0].click();
                            return true;
                        } catch (e) {
                            // Если обычный клик не работает, пробуем dispatchEvent
                            const event = new MouseEvent('click', {
                                view: window,
                                bubbles: true,
                                cancelable: true
                            });
                            arguments[0].dispatchEvent(event);
                            return true;
                        }
                        """,
                        show_more_button
                    )
                    if not click_success:
                        # Fallback: обычный клик через Selenium
                        await loop.run_in_executor(None, show_more_button.click)
                except Exception as click_error:
                    error_msg = str(click_error).lower()
                    if "click intercepted" in error_msg or "not clickable" in error_msg:
                        # Последняя попытка: клик через координаты
                        print(f"Ошибка при клике на 'Показать больше': {click_error}")
                        print("   Пропускаем нажатие на кнопку, пробуем парсить доступные карты")
                    else:
                        print(f"Ошибка при обработке кнопки 'Показать больше': {click_error}")

                await self.random_delay(1.5, 2.5)

                # Прокрутка после нажатия
                await loop.run_in_executor(
                    None,
                    driver.execute_script,
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
                await self.random_delay(0.5, 1.0)

                # Парсим третий блок со скрытыми картами (если они загрузились)
                try:
                    third_block_cards = await self._extract_third_block_cards(driver)
                    if third_block_cards:
                        cards.extend(third_block_cards)
                        print(f"Найдено карт в третьем блоке: {len(third_block_cards)}")
                except Exception as third_block_error:
                    print(f"Не удалось извлечь карты из третьего блока: {third_block_error}")
        except Exception as e:
            error_msg = str(e).lower()
            if "click intercepted" not in error_msg and "not clickable" not in error_msg:
                print(f"Ошибка при обработке кнопки 'Показать больше': {e}")
            # Продолжаем работу, даже если кнопка не была нажата

        # Убираем дубликаты по названию
        unique_cards = []
        seen_titles = set()
        for card in cards:
            title = card.get("title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_cards.append(card)
            elif not title:
                unique_cards.append(card)

        return unique_cards

    async def _extract_all_cards_universal(self, driver: WebDriver) -> list[dict[str, Any]]:
        """
        Универсальный метод извлечения всех карт по известным названиям.
        Более надежный способ, который ищет карты по их названиям в тексте страницы.
        """
        loop = asyncio.get_event_loop()

        # Список всех известных карт с их характеристиками
        known_cards = [
            {'title': 'СберКарта', 'keywords': ['СберКарта'], 'exclude': ['Молодёжная', 'Детская', 'Ветерана', 'Тревел', 'Первый']},
            {'title': 'Платёжный стикер', 'keywords': ['Платёжный', 'стикер'], 'exclude': []},
            {'title': 'Молодёжная СберКарта', 'keywords': ['Молодёжная', 'СберКарта'], 'exclude': []},
            {'title': 'Детская СберКарта', 'keywords': ['Детская', 'СберКарта'], 'exclude': []},
            {'title': 'СберКарта Мир для пособий и пенсии', 'keywords': ['Мир', 'пособий', 'пенсии'], 'exclude': []},
            {'title': 'СберКарта Тревел', 'keywords': ['Тревел', 'СберКарта'], 'exclude': []},
            {'title': 'СберКарта Ветерана', 'keywords': ['Ветерана', 'СберКарта'], 'exclude': []},
            {'title': 'СберПервый х Аэрофлот', 'keywords': ['Первый', 'Аэрофлот'], 'exclude': []},
            {'title': 'МИР Золотая карта Аэрофлот', 'keywords': ['Золотая', 'Аэрофлот'], 'exclude': ['Премиальная']},
            {'title': 'МИР Премиальная карта Аэрофлот', 'keywords': ['Премиальная', 'Аэрофлот'], 'exclude': ['Золотая']},
            {'title': 'СберКарта для иностранцев', 'keywords': ['иностранцев'], 'exclude': []},
            {'title': 'СберКарта «Адафа»', 'keywords': ['Адафа'], 'exclude': []},
            {'title': 'Благотворительная карта Подари жизнь', 'keywords': ['Подари жизнь'], 'exclude': []},
        ]

        card_data_list = await loop.run_in_executor(
            None,
            driver.execute_script,
            """
            const allCards = [];
            const processedTitles = new Set();

            // Список известных карт (определяется выше в Python коде)
            const knownCards = arguments[0];

            // Получаем весь текст страницы для поиска
            const pageText = document.body.textContent || '';

            // Для каждой известной карты
            for (const cardInfo of knownCards) {
                const cardName = cardInfo.title;
                const keywords = cardInfo.keywords || [];
                const exclude = cardInfo.exclude || [];

                if (processedTitles.has(cardName)) continue;

                // Проверяем, есть ли ключевые слова на странице
                let allKeywordsFound = true;
                for (const keyword of keywords) {
                    if (!pageText.includes(keyword)) {
                        allKeywordsFound = false;
                        break;
                    }
                }

                if (!allKeywordsFound) continue;

                // Ищем элемент с названием карты
                const allElements = document.querySelectorAll('*');
                let titleElement = null;

                // Ищем элемент с названием карты более простым способом
                // Используем XPath-подобный поиск через querySelector по тексту
                // Сначала пробуем найти через data-test-id="ZeroBlockTextWidget"
                const textWidgets = document.querySelectorAll('[data-test-id="ZeroBlockTextWidget"]');

                for (const widget of textWidgets) {
                    const text = (widget.textContent || '').trim();
                    if (!text || text.length < 3) continue;

                    // Проверяем наличие всех ключевых слов
                    let matches = true;
                    for (const keyword of keywords) {
                        if (!text.includes(keyword)) {
                            matches = false;
                            break;
                        }
                    }

                    // Проверяем исключения
                    if (matches && exclude.length > 0) {
                        for (const excl of exclude) {
                            if (text.includes(excl)) {
                                matches = false;
                                break;
                            }
                        }
                    }

                    // Дополнительная проверка для "СберКарта"
                    if (matches && keywords.length === 1 && keywords[0] === 'СберКарта') {
                        // Для основной "СберКарта" проверяем, что это не другая карта
                        if (text.includes('Молодёжная') || text.includes('Детская') ||
                            text.includes('Ветерана') || text.includes('Тревел') ||
                            text.includes('Первый') || (text.includes('Мир') && text.includes('пособий') === false)) {
                            matches = false;
                        }
                    }

                    if (matches && text.length <= 200) {
                        titleElement = widget;
                        break;
                    }
                }

                // Если не нашли через виджеты, ищем в любых элементах
                if (!titleElement) {
                    for (const el of allElements) {
                        const text = (el.textContent || '').trim();
                        if (text.length > 0 && text.length < 250) {
                            let matches = true;
                            for (const keyword of keywords) {
                                if (!text.includes(keyword)) {
                                    matches = false;
                                    break;
                                }
                            }
                            if (matches && exclude.length > 0) {
                                for (const excl of exclude) {
                                    if (text.includes(excl)) {
                                        matches = false;
                                        break;
                                    }
                                }
                            }
                            if (matches) {
                                titleElement = el;
                                break;
                            }
                        }
                    }
                }

                if (!titleElement) continue;

                // Получаем точное название из текста элемента
                let exactTitle = (titleElement.textContent || '').trim();

                // Если текст слишком длинный, пробуем найти более короткий вариант
                if (exactTitle.length > 200) {
                    // Ищем более короткий текст в этом элементе или дочерних
                    const shortText = Array.from(titleElement.querySelectorAll('*'))
                        .map(el => (el.textContent || '').trim())
                        .find(t => t.length > 5 && t.length < 150 &&
                                  keywords.every(k => t.includes(k)) &&
                                  !exclude.some(e => t.includes(e)));
                    if (shortText) {
                        exactTitle = shortText;
                    } else {
                        exactTitle = exactTitle.substring(0, 150).trim();
                    }
                }

                // Используем оригинальное название карты, если точное название не подходит
                if (exactTitle.length < 3 || exactTitle.length > 200) {
                    exactTitle = cardName;
                }

                if (processedTitles.has(exactTitle)) continue;
                processedTitles.add(exactTitle);
                processedTitles.add(cardName); // Помечаем оригинальное название как обработанное

                // Находим родительский контейнер карточки
                let cardContainer = titleElement;
                let maxDepth = 15;
                let depth = 0;

                while (cardContainer && depth < maxDepth) {
                    cardContainer = cardContainer.parentElement;
                    depth++;
                    if (!cardContainer) break;

                    // Проверяем признаки карточки
                    const hasImage = cardContainer.querySelector && (
                        cardContainer.querySelector('img') ||
                        cardContainer.querySelector('picture') ||
                        cardContainer.querySelector('[data-test-id="ZeroBlockImageWidget"]')
                    );
                    const hasLink = cardContainer.querySelector && cardContainer.querySelector('a[href]');
                    const hasMultipleWidgets = cardContainer.querySelectorAll &&
                                               cardContainer.querySelectorAll('[data-test-id="ZeroBlockTextWidget"]').length > 1;

                    if ((hasImage || hasLink) && (depth > 3 || hasMultipleWidgets)) {
                        break;
                    }
                }

                if (!cardContainer || depth >= maxDepth) continue;

                // Собираем все текстовые элементы в контейнере
                const allTexts = [];
                const walker = document.createTreeWalker(
                    cardContainer,
                    NodeFilter.SHOW_TEXT,
                    null
                );

                let node;
                while (node = walker.nextNode()) {
                    const text = (node.textContent || '').trim();
                    if (text && text.length > 0 && text.length < 500) {
                        // Убираем дубликаты
                        if (!allTexts.includes(text)) {
                            allTexts.push(text);
                        }
                    }
                }

                // Извлекаем описание (самый длинный текст, не название, с ключевыми словами)
                let description = null;
                for (const text of allTexts) {
                    if (text !== exactTitle && text.length > 50 && text.length < 400 && !description) {
                        // Проверяем, является ли это описанием (содержит характерные слова)
                        if (text.includes('Карта') || text.includes('обслуживание') ||
                            text.includes('кешбэк') || text.includes('миль') ||
                            text.includes('детей') || text.includes('возраст') ||
                            text.includes('путешественников') || text.includes('бюджетные') ||
                            text.includes('ветеран') || text.includes('иностранцев') ||
                            text.includes('Аэрофлот') || text.includes('Адафа') ||
                            text.includes('Подари') || text.includes('тяжелобольным')) {
                            description = text;
                            break;
                        }
                    }
                }

                // Извлекаем особенности (тексты с числами, символами, короткие)
                const features = [];
                for (const text of allTexts) {
                    if (text !== exactTitle && text !== description &&
                        text.length > 0 && text.length < 150 &&
                        (text.includes('₽') || text.includes('%') || text.includes('миль') ||
                         text.includes('Кешбэк') || text.includes('Обслуживание') ||
                         text.includes('годовых') || text.includes('мили') ||
                         text.includes('Дизайн') || text.includes('Лимитированные') ||
                         text.includes('полёт') || text.includes('SkyPriority') ||
                         text.includes('фетву') || text.includes('Подари Жизнь') ||
                         text.includes('ЖКУ') || text.includes('переводы'))) {
                        features.push({value: text, label: text});
                    }
                }

                // Извлекаем бейдж (очень короткий текст с ключевыми словами)
                let badge = null;
                for (const text of allTexts) {
                    if (text.length < 50 &&
                        (text.includes('доставим') || text.includes('сегодня') ||
                         text.includes('за обслуживание'))) {
                        badge = text;
                        break;
                    }
                }

                // Ищем ссылки
                const allLinks = Array.from(cardContainer.querySelectorAll('a[href]'));
                let applyLink = null;
                let detailsLink = null;

                for (const link of allLinks) {
                    const href = link.getAttribute('href') || '';
                    const linkText = (link.textContent || '').trim();

                    if (!applyLink && (href.includes('order') || href === '#order' ||
                        linkText.includes('Оформить'))) {
                        applyLink = link.href || href;
                    }

                    if (!detailsLink && href && !href.includes('order') && !href.startsWith('#') &&
                        href !== applyLink) {
                        // Приоритет ссылкам с названиями карт в пути
                        if (href.includes('sberkarta') || href.includes('pay_sticker') ||
                            linkText.includes('Подробнее')) {
                            detailsLink = link.href || href;
                        }
                    }
                }

                allCards.push({
                    title: exactTitle,
                    description: description,
                    badge: badge,
                    features: features.length > 0 ? features : null,
                    apply_link: applyLink,
                    details_link: detailsLink
                });
            }

            return allCards;
            """,
            known_cards
        )

        print(f"Универсальный метод вернул {len(card_data_list)} карт")

        # Нормализуем ссылки
        normalized_cards = []
        for card_dict in card_data_list:
            if card_dict.get("title"):
                card_info = {
                    "title": card_dict.get("title"),
                    "description": card_dict.get("description"),
                    "badge": card_dict.get("badge"),
                    "features": card_dict.get("features"),
                    "apply_link": card_dict.get("apply_link"),
                    "details_link": card_dict.get("details_link")
                }
                # Нормализуем ссылки
                if card_info["apply_link"] and not card_info["apply_link"].startswith("http"):
                    if not card_info["apply_link"].startswith("#"):
                        card_info["apply_link"] = f"https://www.sberbank.ru{card_info['apply_link']}"
                if card_info["details_link"] and not card_info["details_link"].startswith("http"):
                    if not card_info["details_link"].startswith("#"):
                        card_info["details_link"] = f"https://www.sberbank.ru{card_info['details_link']}"
                normalized_cards.append(card_info)

        return normalized_cards

    async def _extract_first_block_cards(self, driver: WebDriver) -> list[dict[str, Any]]:
        """Извлечение карт из первого блока."""
        cards = []
        loop = asyncio.get_event_loop()

        # Используем универсальный подход: ищем карты по их названиям в тексте страницы
        card_data_list = await loop.run_in_executor(
            None,
            driver.execute_script,
            """
            const cards = [];
            const processedCards = new Set();

            // Список известных названий карт из первого блока
            const cardNames = ['СберКарта', 'Платёжный стикер'];

            // Ищем каждую карту по названию
            for (const cardName of cardNames) {
                if (processedCards.has(cardName)) continue;

                // Ищем элемент с названием карты (любым способом)
                const allElements = document.querySelectorAll('*');
                let titleElement = null;

                for (const el of allElements) {
                    const text = (el.textContent || '').trim();
                    // Для "СберКарта" ищем точное совпадение или начало строки
                    if (cardName === 'СберКарта') {
                        if (text === 'СберКарта' || (text.startsWith('СберКарта') && text.length < 20 &&
                            !text.includes('Молодёжная') && !text.includes('Детская') &&
                            !text.includes('Ветерана') && !text.includes('Тревел'))) {
                            titleElement = el;
                            break;
                        }
                    } else if (cardName === 'Платёжный стикер') {
                        if (text.includes('Платёжный стикер') || text === 'Платёжный стикер') {
                            titleElement = el;
                            break;
                        }
                    }
                }

                if (!titleElement) continue;
                processedCards.add(cardName);

                // Находим родительский контейнер карточки (поднимаемся вверх до контейнера с картинкой или ссылками)
                let cardContainer = titleElement;
                for (let i = 0; i < 15; i++) {
                    cardContainer = cardContainer.parentElement;
                    if (!cardContainer) break;

                    // Проверяем, содержит ли контейнер картинку или ссылку - значит это карточка
                    const hasImage = cardContainer.querySelector && (
                        cardContainer.querySelector('img') ||
                        cardContainer.querySelector('picture') ||
                        cardContainer.querySelector('[data-test-id="ZeroBlockImageWidget"]')
                    );
                    const hasLink = cardContainer.querySelector && cardContainer.querySelector('a[href]');

                    if (hasImage || hasLink) {
                        break;
                    }
                }

                if (!cardContainer) continue;

                // Собираем все текстовые элементы в контейнере
                const allTextElements = [];
                const walker = document.createTreeWalker(
                    cardContainer,
                    NodeFilter.SHOW_TEXT,
                    null
                );

                let node;
                while (node = walker.nextNode()) {
                    const text = (node.textContent || '').trim();
                    if (text && text.length > 0 && text.length < 500) {
                        allTextElements.push({
                            text: text,
                            element: node.parentElement
                        });
                    }
                }

                // Извлекаем данные
                let description = null;
                let badge = null;

                for (const item of allTextElements) {
                    const text = item.text;

                    // Описание для СберКарты
                    if (cardName === 'СберКарта') {
                        if ((text.includes('Бесплатное обслуживание') ||
                             text.includes('выгодная оплата') ||
                             text.includes('ЖКУ') ||
                             (text.length > 60 && text.length < 200 && !text.includes('СберКарта') &&
                              !text.includes('доставим'))) && !description) {
                            description = text;
                        }
                        // Бейдж
                        if (text.includes('доставим сегодня')) {
                            badge = text;
                        }
                    }
                    // Описание для Платёжного стикера
                    else if (cardName === 'Платёжный стикер') {
                        if ((text.includes('Все преимущества СберКарты') ||
                             text.includes('формате стикера') ||
                             text.includes('Наклейте его на смартфон') ||
                             (text.length > 60 && text.length < 200 && !text.includes('Платёжный'))) && !description) {
                            description = text;
                        }
                        // Бейдж
                        if (text.includes('₽ за обслуживание') || text.includes('0 ₽')) {
                            badge = text;
                        }
                    }
                }

                // Ссылки
                const allLinks = Array.from(cardContainer.querySelectorAll('a[href]'));
                let applyLink = null;
                let detailsLink = null;

                for (const link of allLinks) {
                    const href = link.getAttribute('href') || '';
                    const linkText = (link.textContent || '').trim();

                    if (!applyLink && (href.includes('order') || href === '#order' ||
                        linkText.includes('Оформить'))) {
                        applyLink = link.href || href;
                    }

                    if (!detailsLink && href && !href.includes('order') && !href.startsWith('#') &&
                        (href.includes('sberkarta') || linkText.includes('Подробнее'))) {
                        // Для СберКарты ищем ссылку на /sberkarta
                        if (cardName === 'СберКарта' && href.includes('/sberkarta') && !href.includes('pay_sticker')) {
                            detailsLink = link.href || href;
                        }
                        // Для стикера - на /pay_sticker
                        else if (cardName === 'Платёжный стикер' && href.includes('pay_sticker') && !href.includes('order')) {
                            detailsLink = link.href || href;
                        }
                        // Или просто ссылку "Подробнее"
                        else if (linkText.includes('Подробнее')) {
                            detailsLink = link.href || href;
                        }
                    }
                }

                cards.push({
                    title: cardName,
                    description: description,
                    badge: badge,
                    apply_link: applyLink,
                    details_link: detailsLink
                });
            }

            return cards;
            """
        )

        for card_dict in card_data_list:
            if card_dict.get("title"):
                card_info = {
                    "title": card_dict.get("title"),
                    "description": card_dict.get("description"),
                    "badge": card_dict.get("badge"),
                    "features": None,
                    "apply_link": card_dict.get("apply_link"),
                    "details_link": card_dict.get("details_link")
                }
                # Нормализуем ссылки
                if card_info["apply_link"] and not card_info["apply_link"].startswith("http"):
                    if not card_info["apply_link"].startswith("#"):
                        card_info["apply_link"] = f"https://www.sberbank.ru{card_info['apply_link']}"
                if card_info["details_link"] and not card_info["details_link"].startswith("http"):
                    card_info["details_link"] = f"https://www.sberbank.ru{card_info['details_link']}"
                cards.append(card_info)

        return cards

    async def _extract_second_block_cards(self, driver: WebDriver) -> list[dict[str, Any]]:
        """Извлечение карт из второго блока."""
        cards = []
        loop = asyncio.get_event_loop()

        # Используем универсальный подход: ищем карты по известным названиям
        card_data_list = await loop.run_in_executor(
            None,
            driver.execute_script,
            """
            const cards = [];
            const processedTitles = new Set();

            // Известные карты второго блока (видимые без нажатия "Показать больше")
            const secondBlockCardNames = [
                'Молодёжная СберКарта',
                'Детская СберКарта',
                'СберКарта Мир для пособий и пенсии',
                'СберКарта Тревел'
            ];

            // Ищем каждую карту по названию
            for (const fullCardName of secondBlockCardNames) {
                // Определяем ключевые слова для поиска
                let searchKeywords = [];
                if (fullCardName.includes('Молодёжная')) {
                    searchKeywords = ['Молодёжная', 'СберКарта'];
                } else if (fullCardName.includes('Детская')) {
                    searchKeywords = ['Детская', 'СберКарта'];
                } else if (fullCardName.includes('Мир') && fullCardName.includes('пособий')) {
                    searchKeywords = ['Мир', 'пособий', 'пенсии'];
                } else if (fullCardName.includes('Тревел')) {
                    searchKeywords = ['Тревел', 'СберКарта'];
                }

                // Ищем элемент, содержащий название карты
                const allElements = document.querySelectorAll('*');
                let titleElement = null;

                for (const el of allElements) {
                    const text = (el.textContent || '').trim();
                    if (text.length > 0 && text.length < 150) {
                        // Проверяем, содержит ли текст ключевые слова
                        let matches = true;
                        for (const keyword of searchKeywords) {
                            if (!text.includes(keyword)) {
                                matches = false;
                                break;
                            }
                        }

                        if (matches && !text.includes('Ветерана') && !text.includes('Первый') &&
                            !text.includes('Аэрофлот') && !text.includes('Адафа') &&
                            !text.includes('Подари жизнь')) {
                            titleElement = el;
                            break;
                        }
                    }
                }

                if (!titleElement) continue;

                // Получаем точное название из текста
                const exactTitle = (titleElement.textContent || '').trim();
                if (processedTitles.has(exactTitle)) continue;
                processedTitles.add(exactTitle);

                // Находим родительский контейнер карточки
                let cardContainer = titleElement;
                for (let i = 0; i < 15; i++) {
                    cardContainer = cardContainer.parentElement;
                    if (!cardContainer) break;

                    const hasImage = cardContainer.querySelector && (
                        cardContainer.querySelector('img') ||
                        cardContainer.querySelector('picture') ||
                        cardContainer.querySelector('[data-test-id="ZeroBlockImageWidget"]')
                    );
                    const hasLink = cardContainer.querySelector && cardContainer.querySelector('a[href]');

                    if (hasImage || hasLink) {
                        break;
                    }
                }

                if (!cardContainer) continue;

                // Собираем все текстовые элементы в контейнере
                const allTextElements = [];
                const walker = document.createTreeWalker(
                    cardContainer,
                    NodeFilter.SHOW_TEXT,
                    null
                );

                let node;
                while (node = walker.nextNode()) {
                    const text = (node.textContent || '').trim();
                    if (text && text.length > 0 && text.length < 500) {
                        allTextElements.push(text);
                    }
                }

                // Извлекаем данные
                let description = null;
                const features = [];

                for (const text of allTextElements) {
                    // Описание (длинный текст с ключевыми словами)
                    if (!description && text.length > 50 && text.length < 300 &&
                        text !== exactTitle &&
                        (text.includes('Карта') || text.includes('детей') ||
                         text.includes('путешественников') || text.includes('бюджетные') ||
                         text.includes('возраст') || text.includes('кешбэком'))) {
                        description = text;
                    }

                    // Особенности (короткие тексты с числами, символами)
                    if (text !== exactTitle && text !== description &&
                        text.length > 0 && text.length < 100 &&
                        (text.includes('₽') || text.includes('%') || text.includes('миль') ||
                         text.includes('Кешбэк') || text.includes('Обслуживание') ||
                         text.includes('Дизайн') || text.includes('годовых') ||
                         text.includes('Лимитированные'))) {
                        features.push({value: text, label: text});
                    }
                }

                // Ссылки
                const allLinks = Array.from(cardContainer.querySelectorAll('a[href]'));
                let applyLink = null;
                let detailsLink = null;

                for (const link of allLinks) {
                    const href = link.getAttribute('href') || '';
                    const linkText = (link.textContent || '').trim();

                    if (!applyLink && (href.includes('order') || href === '#order' ||
                        linkText.includes('Оформить'))) {
                        applyLink = link.href || href;
                    }

                    if (!detailsLink && href && !href.includes('order') && !href.startsWith('#') &&
                        href !== applyLink && (linkText.includes('Подробнее') || href.includes('/'))) {
                        detailsLink = link.href || href;
                    }
                }

                cards.push({
                    title: exactTitle,
                    description: description,
                    features: features.length > 0 ? features : null,
                    badge: null,
                    apply_link: applyLink,
                    details_link: detailsLink
                });
            }

            return cards;
            """
        )

        for card_dict in card_data_list:
            if card_dict.get("title"):
                card_data = {
                    "title": card_dict.get("title"),
                    "description": card_dict.get("description"),
                    "features": card_dict.get("features"),
                    "badge": card_dict.get("badge"),
                    "apply_link": card_dict.get("apply_link"),
                    "details_link": card_dict.get("details_link")
                }
                # Нормализуем ссылки
                if card_data["apply_link"] and not card_data["apply_link"].startswith("http") and not card_data["apply_link"].startswith("#"):
                    card_data["apply_link"] = f"https://www.sberbank.ru{card_data['apply_link']}"
                if card_data["details_link"] and not card_data["details_link"].startswith("http") and not card_data["details_link"].startswith("#"):
                    card_data["details_link"] = f"https://www.sberbank.ru{card_data['details_link']}"
                cards.append(card_data)

        return cards

    async def _extract_third_block_cards(self, driver: WebDriver) -> list[dict[str, Any]]:
        """Извлечение карт из третьего блока (после нажатия "Показать больше")."""
        cards = []
        loop = asyncio.get_event_loop()

        # Используем универсальный подход: ищем карты по известным названиям
        card_data_list = await loop.run_in_executor(
            None,
            driver.execute_script,
            """
            const cards = [];
            const processedTitles = new Set();

            // Известные карты третьего блока (скрытые, появляются после "Показать больше")
            const thirdBlockCardNames = [
                'СберКарта Ветерана',
                'СберПервый х Аэрофлот',
                'МИР Золотая карта Аэрофлот',
                'МИР Премиальная карта Аэрофлот',
                'СберКарта для иностранцев',
                'СберКарта «Адафа»',
                'Благотворительная карта Подари жизнь'
            ];

            // Ищем каждую карту по названию
            for (const fullCardName of thirdBlockCardNames) {
                // Определяем ключевые слова для поиска
                let searchKeywords = [];
                if (fullCardName.includes('Ветерана')) {
                    searchKeywords = ['Ветерана', 'СберКарта'];
                } else if (fullCardName.includes('Первый') && fullCardName.includes('Аэрофлот')) {
                    searchKeywords = ['Первый', 'Аэрофлот'];
                } else if (fullCardName.includes('Золотая') && fullCardName.includes('Аэрофлот')) {
                    searchKeywords = ['Золотая', 'Аэрофлот', 'МИР'];
                } else if (fullCardName.includes('Премиальная') && fullCardName.includes('Аэрофлот')) {
                    searchKeywords = ['Премиальная', 'Аэрофлот', 'МИР'];
                } else if (fullCardName.includes('иностранцев')) {
                    searchKeywords = ['иностранцев', 'СберКарта'];
                } else if (fullCardName.includes('Адафа')) {
                    searchKeywords = ['Адафа'];
                } else if (fullCardName.includes('Подари жизнь')) {
                    searchKeywords = ['Подари жизнь', 'Благотворительная'];
                }

                // Ищем элемент, содержащий название карты
                const allElements = document.querySelectorAll('*');
                let titleElement = null;

                for (const el of allElements) {
                    const text = (el.textContent || '').trim();
                    if (text.length > 0 && text.length < 200) {
                        // Проверяем, содержит ли текст ключевые слова
                        let matches = true;
                        for (const keyword of searchKeywords) {
                            if (!text.includes(keyword)) {
                                matches = false;
                                break;
                            }
                        }

                        if (matches) {
                            // Дополнительная проверка для точности
                            if (fullCardName.includes('Ветерана') && !text.includes('ветеран')) continue;
                            if (fullCardName.includes('Адафа') && !text.includes('Адафа')) continue;

                            titleElement = el;
                            break;
                        }
                    }
                }

                if (!titleElement) continue;

                // Получаем точное название из текста
                const exactTitle = (titleElement.textContent || '').trim();
                if (processedTitles.has(exactTitle) || exactTitle.length > 200) continue;
                processedTitles.add(exactTitle);

                // Находим родительский контейнер карточки
                let cardContainer = titleElement;
                for (let i = 0; i < 15; i++) {
                    cardContainer = cardContainer.parentElement;
                    if (!cardContainer) break;

                    const hasImage = cardContainer.querySelector && (
                        cardContainer.querySelector('img') ||
                        cardContainer.querySelector('picture') ||
                        cardContainer.querySelector('[data-test-id="ZeroBlockImageWidget"]')
                    );
                    const hasLink = cardContainer.querySelector && cardContainer.querySelector('a[href]');

                    if (hasImage || hasLink) {
                        break;
                    }
                }

                if (!cardContainer) continue;

                // Собираем все текстовые элементы в контейнере
                const allTextElements = [];
                const walker = document.createTreeWalker(
                    cardContainer,
                    NodeFilter.SHOW_TEXT,
                    null
                );

                let node;
                while (node = walker.nextNode()) {
                    const text = (node.textContent || '').trim();
                    if (text && text.length > 0 && text.length < 500) {
                        allTextElements.push(text);
                    }
                }

                // Извлекаем данные
                let description = null;
                const features = [];

                for (const text of allTextElements) {
                    // Описание (длинный текст)
                    if (!description && text.length > 50 && text.length < 400 &&
                        text !== exactTitle &&
                        (text.includes('Карта') || text.includes('ветеран') ||
                         text.includes('Аэрофлот') || text.includes('иностранцев') ||
                         text.includes('Адафа') || text.includes('Подари') ||
                         text.includes('детей') || text.includes('тяжелобольным') ||
                         text.includes('шариата') || text.includes('привилегиями'))) {
                        description = text;
                    }

                    // Особенности (короткие тексты с числами, символами)
                    if (text !== exactTitle && text !== description &&
                        text.length > 0 && text.length < 150 &&
                        (text.includes('₽') || text.includes('%') || text.includes('миль') ||
                         text.includes('Кешбэк') || text.includes('Обслуживание') ||
                         text.includes('годовых') || text.includes('мили') ||
                         text.includes('полёт') || text.includes('SkyPriority') ||
                         text.includes('фетву') || text.includes('Подари Жизнь'))) {
                        features.push({value: text, label: text});
                    }
                }

                // Ссылки
                const allLinks = Array.from(cardContainer.querySelectorAll('a[href]'));
                let applyLink = null;
                let detailsLink = null;

                for (const link of allLinks) {
                    const href = link.getAttribute('href') || '';
                    const linkText = (link.textContent || '').trim();

                    if (!applyLink && (href.includes('order') ||
                        linkText.includes('Оформить'))) {
                        applyLink = link.href || href;
                    }

                    if (!detailsLink && href && !href.includes('order') && !href.startsWith('#') &&
                        href !== applyLink && (linkText.includes('Подробнее') || href.includes('/'))) {
                        detailsLink = link.href || href;
                    }
                }

                cards.push({
                    title: exactTitle,
                    description: description,
                    features: features.length > 0 ? features : null,
                    badge: null,
                    apply_link: applyLink,
                    details_link: detailsLink
                });
            }

            return cards;
            """
        )

        for card_dict in card_data_list:
            if card_dict.get("title"):
                card_info = {
                    "title": card_dict.get("title"),
                    "description": card_dict.get("description"),
                    "features": card_dict.get("features"),
                    "badge": card_dict.get("badge"),
                    "apply_link": card_dict.get("apply_link"),
                    "details_link": card_dict.get("details_link")
                }
                # Нормализуем ссылки
                if card_info["apply_link"] and not card_info["apply_link"].startswith("http") and not card_info["apply_link"].startswith("#"):
                    card_info["apply_link"] = f"https://www.sberbank.ru{card_info['apply_link']}"
                if card_info["details_link"] and not card_info["details_link"].startswith("http") and not card_info["details_link"].startswith("#"):
                    card_info["details_link"] = f"https://www.sberbank.ru{card_info['details_link']}"
                cards.append(card_info)

        return cards
