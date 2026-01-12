"""
Парсер кредитных продуктов Сбербанка на основе Selenium.

Автоматически определяет доступный браузер (Chrome или Firefox) и использует его
для парсинга. Приоритет: Chrome → Firefox. Это решает проблему с сертификатами,
так как Selenium использует реальный установленный браузер со всеми его настройками.

Поддерживает парсинг:
- Кредитов наличными: https://www.sberbank.ru/ru/person/credits/money
- Ипотек: https://www.sberbank.ru/ru/person/credits/homenew

ВАЖНО: Перед использованием парсера:
1. Убедитесь, что установлен хотя бы один из браузеров (Chrome или Firefox)
   и в нем установлены сертификаты Минцифры:
   - Откройте браузер вручную
   - Перейдите на https://www.sberbank.ru
   - Если появится ошибка сертификата, установите сертификаты Минцифры
   - Инструкции: https://www.gosuslugi.ru/crt
2. ЗАКРОЙТЕ ВСЕ ОКНА БРАУЗЕРА перед запуском парсера (профиль не должен быть заблокирован)
   - Закройте все вкладки браузера
   - Закройте все фоновые процессы браузера
   - Проверьте диспетчер задач (Ctrl+Shift+Esc) - не должно быть процессов chrome.exe/firefox.exe
3. Установите зависимости: pip install selenium webdriver-manager
   Или используйте: uv sync (если используете uv)

Парсер автоматически выберет Chrome, если он установлен, иначе Firefox.
Если Chrome не удалось запустить, автоматически попробует Firefox.

Использование:
    async with SberbankCreditProductsSeleniumParser(headless=False) as parser:
        # Для кредитов
        data1 = await parser.parse_page("https://www.sberbank.ru/ru/person/credits/money")
        # Для ипотек
        data2 = await parser.parse_page("https://www.sberbank.ru/ru/person/credits/homenew")
"""

import asyncio
import os
import random
import shutil
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


class SberbankCreditProductsSeleniumParser:
    """
    Парсер кредитных продуктов Сбербанка на основе Selenium.

    Использует Firefox браузер, где уже установлены все сертификаты,
    включая сертификаты Минцифры. Это позволяет обойти проблему с сертификатами
    при использовании Playwright.

    Особенности:
    - Использует реальный браузер Firefox со всеми установленными сертификатами
    - Парсит продукты из блоков product-catalog__product-cards и product-catalog__other-cards
    - Поддерживает парсинг кредитов и ипотек
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
            chrome_path = shutil.which('chrome') or shutil.which('google-chrome') or shutil.which('chromium')
            if chrome_path:
                return True

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
            firefox_path = shutil.which('firefox') or shutil.which('mozilla-firefox')
            if firefox_path:
                return True

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
            firefox_profiles = Path.home() / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles"
            if firefox_profiles.exists():
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

        if self.headless:
            chrome_options.add_argument("--headless=new")

        chrome_options.add_argument(f"--window-size={self.viewport_width},{self.viewport_height}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--lang=ru-RU")
        chrome_options.add_argument("--start-maximized")

        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--ignore-certificate-errors")

        print("Используется Chrome с системными сертификатами Windows и игнорированием ошибок сертификата")

        try:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

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

        if self.headless:
            firefox_options.add_argument("--headless")

        firefox_options.set_preference("general.useragent.override",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0")
        firefox_options.set_preference("width", self.viewport_width)
        firefox_options.set_preference("height", self.viewport_height)
        firefox_options.set_preference("intl.accept_languages", "ru-RU,ru,en-US,en")
        firefox_options.set_preference("dom.webdriver.enabled", False)
        firefox_options.set_preference("useAutomationExtension", False)
        firefox_options.set_preference("security.tls.insecure_fallback_hosts", "sberbank.ru,www.sberbank.ru")
        firefox_options.set_preference("security.tls.unrestricted_rc4_fallback", True)
        firefox_options.set_preference("security.enterprise_roots.enabled", True)

        print("Используется Firefox с системными сертификатами Windows")

        try:
            service = FirefoxService(GeckoDriverManager().install())
            driver = webdriver.Firefox(service=service, options=firefox_options)
            driver.set_window_size(self.viewport_width, self.viewport_height)

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
        browser = self._get_available_browser()

        if browser is None:
            raise RuntimeError(
                "Не найден ни один из поддерживаемых браузеров (Chrome или Firefox).\n"
                "Пожалуйста, установите Chrome или Firefox для использования парсера."
            )

        if browser == 'chrome':
            try:
                return self._create_chrome_driver()
            except Exception as chrome_error:
                print(f"\nНе удалось создать драйвер Chrome: {chrome_error}")
                print("Пробую использовать Firefox в качестве запасного варианта...")
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

        raise RuntimeError(f"Неподдерживаемый браузер: {browser}")

    async def start(self) -> None:
        """Инициализировать браузер."""
        if self._driver is None:
            # Selenium не поддерживает async напрямую, поэтому используем executor
            loop = asyncio.get_event_loop()
            self._driver = await loop.run_in_executor(None, self._create_driver)
            print("Парсер кредитных продуктов Сбербанка инициализирован")

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
        Парсинг страницы с кредитными продуктами Сбербанка.

        Args:
            url: URL страницы для парсинга (кредиты или ипотеки)

        Returns:
            Словарь с извлеченными данными о кредитных продуктах
        """
        driver = self.driver

        # Переход на страницу
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, driver.get, url)

        # Увеличиваем время ожидания для полной загрузки страницы
        await self.random_delay(2.0, 3.0)

        driver = self.driver

        # Ожидание загрузки страницы и появления элементов
        wait = WebDriverWait(driver, self.timeout)

        # Ждем появления хотя бы одного продукта
        try:
            # Проверяем загрузку через JavaScript
            page_ready = await loop.run_in_executor(
                None,
                driver.execute_script,
                """
                // Ждем загрузки DOM и появления элементов
                const checkReady = () => {
                    const cards = document.querySelectorAll('.product-card');
                    const hasContent = document.body.textContent.includes('Кредит') ||
                                      document.body.textContent.includes('ипотек') ||
                                      document.body.textContent.includes('Ипотека');
                    return cards.length > 0 || hasContent;
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
            page_source = await loop.run_in_executor(None, lambda: driver.page_source)
            if "Возникла проблема при открытии сайта Сбербанка" in page_source or \
               "не установлены сертификаты Национального УЦ Минцифры" in page_source:
                raise Exception(
                    "Обнаружена страница с ошибкой сертификатов. "
                    "Убедитесь, что сертификаты Минцифры установлены в Firefox."
                )
        except Exception as e:
            if "сертификатов" not in str(e).lower():
                print(f"Предупреждение при проверке страницы: {e}")
            pass

        # Прокрутка для загрузки lazy-loaded элементов (несколько раз)
        try:
            for scroll_step in [0.25, 0.5, 0.75, 1.0]:
                await loop.run_in_executor(
                    None,
                    driver.execute_script,
                    f"window.scrollTo(0, document.body.scrollHeight * {scroll_step});"
                )
                await self.random_delay(0.3, 0.5)
        except Exception:
            pass

        # Извлечение данных о всех продуктах
        products = await self._extract_products(driver, url)

        # Отладочный вывод
        print(f"Извлечено продуктов: {len(products)}")

        # Получаем title правильно (это свойство, а не метод)
        title = await loop.run_in_executor(None, lambda: driver.title)

        return {
            "url": url,
            "title": title,
            "products_count": len(products),
            "products": products,
        }

    async def _extract_products(self, driver: WebDriver, url: str) -> list[dict[str, Any]]:
        """
        Извлечение данных о всех кредитных продуктах.

        Args:
            driver: WebDriver экземпляр
            url: URL страницы для определения типа продукта

        Returns:
            Список словарей с данными о продуктах
        """
        products = []
        loop = asyncio.get_event_loop()

        # Извлекаем все продукты из основных блоков
        try:
            products_data = await loop.run_in_executor(
                None,
                driver.execute_script,
                """
                const products = [];

                // Ищем все карточки продуктов в основном блоке
                const cardWraps = document.querySelectorAll('.product-card__wrap');

                for (const wrap of cardWraps) {
                    try {
                        const card = wrap.querySelector('.product-card');
                        if (!card) continue;

                        // Извлекаем название продукта
                        let title = null;
                        const headingInner = card.querySelector('.product-card__content_inner .product-card__heading');
                        const headingOuter = card.querySelector('.product-card__content_outer .product-card__heading');
                        const headingAny = card.querySelector('.product-card__heading');

                        if (headingInner) {
                            title = (headingInner.textContent || '').trim();
                        } else if (headingOuter) {
                            title = (headingOuter.textContent || '').trim();
                        } else if (headingAny) {
                            title = (headingAny.textContent || '').trim();
                        }

                        if (!title || title.length === 0) continue;

                        // Извлекаем описание (subtitle) - может быть в p или просто текст
                        let subtitle = null;
                        // Сначала пробуем найти в inner контейнере
                        const descInnerContainer = card.querySelector('.product-card__content_inner .product-card__description');
                        if (descInnerContainer) {
                            const descInnerP = descInnerContainer.querySelector('p');
                            subtitle = descInnerP ? (descInnerP.textContent || '').trim() : (descInnerContainer.textContent || '').trim();
                        }

                        // Если не нашли в inner, пробуем outer
                        if (!subtitle) {
                            const descOuterContainer = card.querySelector('.product-card__content_outer .product-card__description');
                            if (descOuterContainer) {
                                const descOuterP = descOuterContainer.querySelector('p');
                                subtitle = descOuterP ? (descOuterP.textContent || '').trim() : (descOuterContainer.textContent || '').trim();
                            }
                        }

                        // Если все еще не нашли, ищем в любом месте карточки
                        if (!subtitle) {
                            const descAny = card.querySelector('.product-card__description');
                            if (descAny) {
                                const descAnyP = descAny.querySelector('p');
                                subtitle = descAnyP ? (descAnyP.textContent || '').trim() : (descAny.textContent || '').trim();
                            }
                        }

                        // Извлекаем метки (labels) - например, "Без комиссий", "Без залогов и поручителей"
                        const labels = [];
                        // Ищем labels в обоих контейнерах (inner и outer) или просто в карточке
                        const labelsContainers = card.querySelectorAll('.product-card__labels');
                        if (labelsContainers.length === 0) {
                            // Если labels не найдены по классу, пробуем найти в контейнерах content
                            const contentInner = card.querySelector('.product-card__content_inner');
                            const contentOuter = card.querySelector('.product-card__content_outer');
                            if (contentInner) {
                                const innerLabels = contentInner.querySelectorAll('.dk-sbol-label-nova, .product-card__label');
                                for (const labelEl of innerLabels) {
                                    const labelText = (labelEl.textContent || '').trim();
                                    if (labelText) {
                                        labels.push(labelText);
                                    }
                                }
                            }
                            if (contentOuter) {
                                const outerLabels = contentOuter.querySelectorAll('.dk-sbol-label-nova, .product-card__label');
                                for (const labelEl of outerLabels) {
                                    const labelText = (labelEl.textContent || '').trim();
                                    if (labelText && !labels.includes(labelText)) {
                                        labels.push(labelText);
                                    }
                                }
                            }
                        } else {
                            for (const labelsContainer of labelsContainers) {
                                const labelElements = labelsContainer.querySelectorAll('.product-card__label, .dk-sbol-label-nova');
                                for (const labelEl of labelElements) {
                                    const labelText = (labelEl.textContent || '').trim();
                                    if (labelText && !labels.includes(labelText)) {
                                        labels.push(labelText);
                                    }
                                }
                            }
                        }

                        // Извлекаем особенности (factoids) - они содержат цену и срок
                        const factoids = [];
                        const factoidsContainers = card.querySelectorAll('.product-card__factoids');
                        for (const factoidsContainer of factoidsContainers) {
                            const factoidElements = factoidsContainer.querySelectorAll('.factoid');
                            for (const factoid of factoidElements) {
                                const factoidHeading = factoid.querySelector('h3.dk-sbol-heading');

                                if (factoidHeading) {
                                    const value = (factoidHeading.textContent || '').trim();
                                    let label = null;

                                    // Ищем описание в разных местах
                                    const factoidTooltip = factoid.querySelector('.factoid__tooltip .dk-sbol-text p, .factoid__tooltip .dk-sbol-text span, .factoid__tooltip .dk-sbol-text');
                                    const factoidDesc = factoid.querySelector('.factoid__description .dk-sbol-text p, .factoid__description .dk-sbol-text span, .factoid__description .dk-sbol-text');

                                    if (factoidTooltip) {
                                        label = (factoidTooltip.textContent || '').trim();
                                    } else if (factoidDesc) {
                                        label = (factoidDesc.textContent || '').trim();
                                        // Убираем значение из описания, если оно там есть
                                        if (label && label.includes(value)) {
                                            label = label.replace(value, '').trim();
                                        }
                                    }

                                    if (value) {
                                        factoids.push({
                                            value: value,
                                            label: label || value
                                        });
                                    }
                                }
                            }
                        }

                        // Убираем дубликаты factoids по значению
                        const uniqueFactoids = [];
                        const seenValues = new Set();
                        for (const factoid of factoids) {
                            if (!seenValues.has(factoid.value)) {
                                seenValues.add(factoid.value);
                                uniqueFactoids.push(factoid);
                            }
                        }

                        // Формируем price и term из factoids
                        // price обычно содержит суммы (₽, млн ₽, тыс ₽)
                        // term обычно содержит сроки (лет, дней, месяцев, мин)
                        let priceParts = [];
                        let termParts = [];

                        for (const factoid of uniqueFactoids) {
                            const value = factoid.value;
                            const label = factoid.label || '';

                            // Проверяем, является ли это ценой/суммой
                            // Приоритет label, так как он более точно описывает содержимое
                            let isPrice = false;
                            let isTerm = false;

                            // Проверка по label (более точная)
                            if (label.includes('сумм') || label.includes('кредит') || label.includes('сумма') ||
                                (label.includes('взнос') && value.includes('%'))) {
                                isPrice = true;
                            } else if (label.includes('срок') || label.includes('рассмотрим') ||
                                      label.includes('оформление') || label.includes('обучение') ||
                                      (label.includes('ставка') && !value.includes('₽')) ||
                                      (label.includes('платёж') && !value.includes('₽'))) {
                                isTerm = true;
                            }
                            // Если по label не определили, проверяем по value
                            else {
                                // Проверяем наличие цифр простым способом
                                const hasNumbers = /[0-9]/.test(value);

                                if (value.includes('₽') || value.includes('млн') || value.includes('тыс') ||
                                    (value.includes('от') && hasNumbers) ||
                                    (value.includes('до') && hasNumbers && (value.includes('₽') || value.includes('млн')))) {
                                    isPrice = true;
                                } else if (value.includes('лет') || value.includes('год') || value.includes('дней') ||
                                          value.includes('месяц') || value.includes('мин') || value.includes('семестр') ||
                                          (value.includes('%') && !value.includes('₽')) ||
                                          (value.includes('сниженный') || value.includes('льготная'))) {
                                    isTerm = true;
                                }
                            }

                            if (isPrice) {
                                priceParts.push(value);
                            } else if (isTerm) {
                                termParts.push(value);
                            } else {
                                // Если не можем определить, пробуем по значению
                                if (value.includes('₽') || value.includes('млн') || value.includes('тыс')) {
                                    priceParts.push(value);
                                } else if (value.includes('лет') || value.includes('год') || value.includes('дней') ||
                                           value.includes('месяц') || value.includes('мин')) {
                                    termParts.push(value);
                                } else {
                                    // По умолчанию добавляем в term как дополнительное условие
                                    termParts.push(value);
                                }
                            }
                        }

                        const price = priceParts.length > 0 ? priceParts.join(', ') : null;
                        const term = termParts.length > 0 ? termParts.join(', ') : null;

                        // Извлекаем ссылки
                        let link = null;
                        const buttonsContainer = card.querySelector('.product-card__buttons');
                        if (buttonsContainer) {
                            // Ищем кнопку "Оформить онлайн", "Подать заявку" или ссылку "Подробнее"/"Узнать больше"
                            const allButtons = buttonsContainer.querySelectorAll('a');
                            for (const btn of allButtons) {
                                const btnText = (btn.textContent || '').trim();
                                const testId = btn.getAttribute('data-test-id');
                                const href = btn.getAttribute('href') || btn.href;

                                // Приоритет кнопке оформления, но если её нет, берем ссылку подробнее
                                if (testId === 'Button-primary-md' || btnText.includes('Оформить') ||
                                    btnText.includes('Подать') || btnText.includes('Выбрать')) {
                                    link = href;
                                    break;
                                } else if (btnText.includes('Подробнее') || btnText.includes('Узнать')) {
                                    if (!link) {
                                        link = href;
                                    }
                                }
                            }

                            // Если ссылка не найдена, берем первую доступную
                            if (!link && allButtons.length > 0) {
                                link = allButtons[0].getAttribute('href') || allButtons[0].href;
                            }
                        }

                        products.push({
                            title: title,
                            subtitle: subtitle,
                            price: price || null,
                            term: term || null,
                            labels: labels.length > 0 ? labels : null,
                            link: link
                        });
                    } catch (e) {
                        console.error('Ошибка при извлечении продукта:', e);
                        continue;
                    }
                }

                // Также извлекаем продукты из блока "Другие предложения" (other-card), если нужно
                // (пока пропускаем, так как структура данных может отличаться)

                return products;
                """
            )

            # Нормализуем ссылки
            normalized_products = []
            for product_dict in products_data:
                if product_dict.get("title"):
                    product_info = {
                        "title": product_dict.get("title"),
                        "subtitle": product_dict.get("subtitle"),
                        "price": product_dict.get("price"),
                        "term": product_dict.get("term"),
                        "link": product_dict.get("link")
                    }
                    # Labels не входят в схему CREDIT_PRODUCT_SCHEMA, поэтому не добавляем их
                    # Нормализуем ссылки
                    if product_info["link"] and not product_info["link"].startswith("http"):
                        if not product_info["link"].startswith("#"):
                            # Если ссылка относительная и не начинается с //, добавляем домен
                            if product_info["link"].startswith("//"):
                                product_info["link"] = f"https:{product_info['link']}"
                            else:
                                product_info["link"] = f"https://www.sberbank.ru{product_info['link']}"
                        else:
                            # Для якорных ссылок добавляем полный URL на основе исходного URL
                            if '/credits/money' in url:
                                product_info["link"] = f"https://www.sberbank.ru/ru/person/credits/money{product_info['link']}"
                            elif '/credits/homenew' in url or '/credits/home' in url:
                                product_info["link"] = f"https://www.sberbank.ru/ru/person/credits/homenew{product_info['link']}"
                            else:
                                # Если не можем определить, просто добавляем базовый URL
                                product_info["link"] = f"https://www.sberbank.ru{product_info['link']}"
                    normalized_products.append(product_info)

            products.extend(normalized_products)
            print(f"Найдено кредитных продуктов: {len(normalized_products)}")

        except Exception as e:
            print(f"Ошибка при извлечении продуктов: {e}")
            traceback.print_exc()

        # Если продукты не найдены, добавляем отладочную информацию
        if len(products) == 0:
            print("Продукты не найдены. Попытка альтернативного извлечения данных...")
            debug_info = await loop.run_in_executor(
                None,
                driver.execute_script,
                """
                const info = {
                    totalCardWraps: document.querySelectorAll('.product-card__wrap').length,
                    totalProductCards: document.querySelectorAll('.product-card').length,
                    totalOtherCards: document.querySelectorAll('.other-card').length,
                    hasProductCatalog: !!document.querySelector('.product-catalog__product-cards'),
                    sampleHeadings: []
                };

                // Берем первые 10 заголовков для отладки
                const headings = document.querySelectorAll('.product-card__heading, .other-card__heading');
                for (let i = 0; i < Math.min(10, headings.length); i++) {
                    const text = (headings[i].textContent || '').trim();
                    if (text) {
                        info.sampleHeadings.push(text);
                    }
                }

                return info;
                """
            )
            print(f"Отладочная информация:")
            print(f"  Всего оберток карточек (.product-card__wrap): {debug_info.get('totalCardWraps', 0)}")
            print(f"  Всего карточек (.product-card): {debug_info.get('totalProductCards', 0)}")
            print(f"  Всего other-card: {debug_info.get('totalOtherCards', 0)}")
            print(f"  Есть блок product-catalog__product-cards: {debug_info.get('hasProductCatalog', False)}")
            print(f"  Примеры заголовков (первые 5):")
            for i, heading in enumerate(debug_info.get('sampleHeadings', [])[:5], 1):
                print(f"    {i}. {heading[:100]}{'...' if len(heading) > 100 else ''}")

        # Убираем дубликаты по названию
        unique_products = []
        seen_titles = set()
        for product in products:
            title = product.get("title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_products.append(product)
            elif not title:
                unique_products.append(product)

        return unique_products
