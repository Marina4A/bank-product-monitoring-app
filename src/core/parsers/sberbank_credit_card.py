"""
Парсер кредитных карт Сбербанка на основе Selenium.

Автоматически определяет доступный браузер (Chrome или Firefox) и использует его
для парсинга. Приоритет: Chrome → Firefox. Это решает проблему с сертификатами,
так как Selenium использует реальный установленный браузер со всеми его настройками.

Поддерживает парсинг кредитных карт из блока product-catalog__product-cards.

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
    async with SberbankCreditCardSeleniumParser(headless=False) as parser:
        data = await parser.parse_page("https://www.sberbank.ru/ru/person/bank_cards/credit_cards")
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


class SberbankCreditCardSeleniumParser:
    """
    Парсер кредитных карт Сбербанка на основе Selenium.

    Автоматически определяет доступный браузер (Chrome или Firefox) и использует его
    для парсинга. Приоритет: Chrome → Firefox. Это позволяет обойти проблему с сертификатами
    при использовании Playwright.

    Особенности:
    - Автоматический выбор браузера (Chrome приоритетен, затем Firefox)
    - Использует реальный браузер со всеми установленными сертификатами
    - Парсит карты из блока product-catalog__product-cards
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
            print("Парсер кредитных карт Сбербанка инициализирован")

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
        Парсинг страницы с кредитными картами Сбербанка.

        Args:
            url: URL страницы для парсинга

        Returns:
            Словарь с извлеченными данными о кредитных картах
        """
        driver = self.driver

        # Переход на страницу
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, driver.get, url)

        # Увеличиваем время ожидания для полной загрузки страницы
        await self.random_delay(3.0, 4.0)

        # Обновляем driver на случай, если был создан новый при обработке ошибок
        driver = self.driver

        # Ожидание загрузки страницы и появления элементов
        wait = WebDriverWait(driver, self.timeout)

        # Ждем появления хотя бы одного текстового виджета или контента
        try:
            # Явно ждем появления карточек через WebDriverWait - увеличиваем timeout
            try:
                await loop.run_in_executor(
                    None,
                    lambda: wait.until(
                        EC.any_of(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".product-card__wrap")),
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".product-card")),
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".product-catalog__product-cards")),
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".product-catalog"))
                        )
                    )
                )
                print("Элементы карточек найдены на странице (WebDriverWait)")
            except Exception as wait_error:
                print(f"Явное ожидание элементов не сработало: {wait_error}, продолжаем...")
                # Дополнительное ожидание вручную
                await self.random_delay(2.0, 3.0)

            # Дополнительная проверка загрузки через JavaScript
            page_ready = await loop.run_in_executor(
                None,
                driver.execute_script,
                """
                // Ждем загрузки DOM и появления элементов
                const checkReady = () => {
                    const cards = document.querySelectorAll('.product-card');
                    const wraps = document.querySelectorAll('.product-card__wrap');
                    const hasContent = document.body.textContent.includes('Карта') ||
                                      document.body.textContent.includes('кредит') ||
                                      document.body.textContent.includes('кредитная');
                    return cards.length > 0 || wraps.length > 0 || hasContent;
                };

                // Ждем до 20 секунд с более частыми проверками
                const startTime = Date.now();
                const maxWait = 20000;
                let lastCheckCount = 0;
                while (Date.now() - startTime < maxWait) {
                    const currentCards = document.querySelectorAll('.product-card');
                    const currentWraps = document.querySelectorAll('.product-card__wrap');
                    const currentCount = currentCards.length + currentWraps.length;

                    // Если количество элементов увеличивается, продолжаем ждать
                    if (currentCount > lastCheckCount) {
                        lastCheckCount = currentCount;
                        console.log(`Найдено элементов: ${currentCount}`);
                    }

                    if (document.readyState === 'complete' && checkReady()) {
                        console.log(`Готово! Найдено элементов: ${currentCount}`);
                        return true;
                    }
                    // Небольшая задержка между проверками
                    const start = Date.now();
                    while (Date.now() - start < 200) {}
                }
                const finalCheck = checkReady();
                console.log(`Финальная проверка: ${finalCheck}, найдено элементов: ${lastCheckCount}`);
                return finalCheck;
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
                    "Убедитесь, что сертификаты Минцифры установлены в браузере."
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

            # Дополнительная задержка для полной загрузки динамического контента
            await self.random_delay(1.5, 2.5)

            # Финальная проверка после прокрутки - ждем появления элементов
            elements_after_scroll = await loop.run_in_executor(
                None,
                driver.execute_script,
                """
                return {
                    cardWraps: document.querySelectorAll('.product-card__wrap').length,
                    productCards: document.querySelectorAll('.product-card').length,
                    hasCatalog: !!document.querySelector('.product-catalog__product-cards, .product-catalog')
                };
                """
            )
            print(f"Элементы после прокрутки:")
            print(f"  .product-card__wrap: {elements_after_scroll.get('cardWraps', 0)}")
            print(f"  .product-card: {elements_after_scroll.get('productCards', 0)}")
            print(f"  Есть каталог: {elements_after_scroll.get('hasCatalog', False)}")

            # Если элементы все еще не найдены, пробуем подождать еще
            if elements_after_scroll.get('cardWraps', 0) == 0 and elements_after_scroll.get('productCards', 0) == 0:
                print("Элементы все еще не найдены после прокрутки, жду еще...")
                await self.random_delay(2.0, 3.0)
                # Еще одна проверка
                elements_final = await loop.run_in_executor(
                    None,
                    driver.execute_script,
                    """
                    return {
                        cardWraps: document.querySelectorAll('.product-card__wrap').length,
                        productCards: document.querySelectorAll('.product-card').length,
                        hasCatalog: !!document.querySelector('.product-catalog__product-cards, .product-catalog')
                    };
                    """
                )
                print(f"Финальная проверка элементов:")
                print(f"  .product-card__wrap: {elements_final.get('cardWraps', 0)}")
                print(f"  .product-card: {elements_final.get('productCards', 0)}")
                print(f"  Есть каталог: {elements_final.get('hasCatalog', False)}")
        except Exception as e:
            print(f"Ошибка при прокрутке страницы: {e}")
            pass

        # Извлечение данных о всех картах
        cards = await self._extract_cards(driver)

        # Отладочный вывод
        print(f"Извлечено карт: {len(cards)}")

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
        Извлечение данных о всех кредитных картах.

        Args:
            driver: WebDriver экземпляр

        Returns:
            Список словарей с данными о картах
        """
        cards = []
        loop = asyncio.get_event_loop()

        # Сначала проверяем, есть ли элементы на странице
        try:
            element_check = await loop.run_in_executor(
                None,
                driver.execute_script,
                """
                return {
                    cardWraps: document.querySelectorAll('.product-card__wrap').length,
                    productCards: document.querySelectorAll('.product-card').length,
                    productCatalog: !!document.querySelector('.product-catalog__product-cards'),
                    hasHeading: document.querySelectorAll('.product-card__heading').length > 0,
                    bodyText: document.body.textContent.substring(0, 500)
                };
                """
            )
            print(f"Проверка элементов на странице:")
            print(f"  .product-card__wrap: {element_check.get('cardWraps', 0)}")
            print(f"  .product-card: {element_check.get('productCards', 0)}")
            print(f"  .product-catalog__product-cards: {element_check.get('productCatalog', False)}")
            print(f"  .product-card__heading: {element_check.get('hasHeading', False)}")
            if element_check.get('cardWraps', 0) == 0 and element_check.get('productCards', 0) == 0:
                print(f"Карточки не найдены! Первые 500 символов страницы: {element_check.get('bodyText', '')[:200]}")
        except Exception as e:
            print(f"Ошибка при проверке элементов: {e}")

        # Извлекаем все карты из блока product-catalog__product-cards
        # Используем тот же подход, что и в кредитных продуктах (который работает)
        try:
            card_data_list = await loop.run_in_executor(
                None,
                driver.execute_script,
                """
                const cards = [];

                // Ищем все карточки продуктов - используем простой подход, как в кредитных продуктах
                // Сначала пробуем через .product-card__wrap
                let cardWraps = Array.from(document.querySelectorAll('.product-card__wrap'));

                console.log(`Найдено .product-card__wrap: ${cardWraps.length}`);

                // Если нет оберток, пробуем найти карточки напрямую
                if (cardWraps.length === 0) {
                    console.log('Обертки не найдены, ищу карточки напрямую...');
                    const directCards = document.querySelectorAll('.product-card');
                    console.log(`Найдено .product-card напрямую: ${directCards.length}`);

                    // Создаем массив оберток из прямых карточек
                    const wrapsArray = [];
                    for (const directCard of directCards) {
                        // Проверяем, что это карточка продукта (не другая карточка)
                        const hasHeading = directCard.querySelector('.product-card__heading');
                        const inCatalog = directCard.closest('.product-catalog__product-cards') ||
                                          directCard.closest('.product-catalog');

                        if (hasHeading || inCatalog) {
                            wrapsArray.push(directCard);
                        }
                    }
                    console.log(`Отфильтровано карточек продуктов: ${wrapsArray.length}`);
                    cardWraps = wrapsArray;
                }

                console.log(`Всего карточек для обработки: ${cardWraps.length}`);

                for (let i = 0; i < cardWraps.length; i++) {
                    try {
                        const wrap = cardWraps[i];
                        let card = wrap.querySelector('.product-card');
                        // Если карточка не найдена внутри wrap, возможно сама wrap является карточкой
                        if (!card && wrap.classList && wrap.classList.contains('product-card')) {
                            card = wrap;
                        }
                        if (!card) {
                            console.log(`Карточка не найдена для wrap ${i + 1}/${cardWraps.length}, пропускаем`);
                            continue;
                        }

                        console.log(`Обрабатываем карточку ${i + 1}/${cardWraps.length}`);

                        // Извлекаем название карты (может быть в двух местах: inner и outer, или просто в карточке)
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

                        // Извлекаем описание (может быть в p или просто текст)
                        let description = null;
                        // Сначала пробуем найти в inner контейнере
                        const descInnerContainer = card.querySelector('.product-card__content_inner .product-card__description');
                        if (descInnerContainer) {
                            const descInnerP = descInnerContainer.querySelector('p');
                            description = descInnerP ? (descInnerP.textContent || '').trim() : (descInnerContainer.textContent || '').trim();
                        }

                        // Если не нашли в inner, пробуем outer
                        if (!description) {
                            const descOuterContainer = card.querySelector('.product-card__content_outer .product-card__description');
                            if (descOuterContainer) {
                                const descOuterP = descOuterContainer.querySelector('p');
                                description = descOuterP ? (descOuterP.textContent || '').trim() : (descOuterContainer.textContent || '').trim();
                            }
                        }

                        // Если все еще не нашли, ищем в любом месте карточки
                        if (!description) {
                            const descAny = card.querySelector('.product-card__description');
                            if (descAny) {
                                const descAnyP = descAny.querySelector('p');
                                description = descAnyP ? (descAnyP.textContent || '').trim() : (descAny.textContent || '').trim();
                            }
                        }

                        // Извлекаем особенности (factoids) - ищем во всех местах карточки
                        const features = [];

                        // Ищем factoids в обоих контейнерах (inner и outer)
                        const factoidsContainers = card.querySelectorAll('.product-card__factoids');
                        for (const factoidsContainer of factoidsContainers) {
                            const factoids = factoidsContainer.querySelectorAll('.factoid');
                            for (const factoid of factoids) {
                                const factoidHeading = factoid.querySelector('h3.dk-sbol-heading');

                                if (factoidHeading) {
                                    const value = (factoidHeading.textContent || '').trim();
                                    let label = null;

                                    // Ищем описание в разных местах - используем тот же подход, что в кредитных продуктах
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
                                        features.push({
                                            value: value,
                                            label: label || value
                                        });
                                    }
                                }
                            }
                        }

                        // Убираем дубликаты особенностей по значению
                        const uniqueFeatures = [];
                        const seenValues = new Set();
                        for (const feature of features) {
                            if (!seenValues.has(feature.value)) {
                                seenValues.add(feature.value);
                                uniqueFeatures.push(feature);
                            }
                        }

                        // Извлекаем ссылки - используем тот же подход, что в кредитных продуктах
                        let applyLink = null;
                        let detailsLink = null;

                        const buttonsContainer = card.querySelector('.product-card__buttons');
                        if (buttonsContainer) {
                            // Ищем все ссылки в контейнере кнопок
                            const allButtons = buttonsContainer.querySelectorAll('a');
                            for (const btn of allButtons) {
                                const btnText = (btn.textContent || '').trim();
                                const testId = btn.getAttribute('data-test-id');
                                const href = btn.getAttribute('href') || btn.href;

                                // Приоритет кнопке оформления, но если её нет, берем ссылку подробнее
                                if (testId === 'Button-primary-md' || btnText.includes('Оформить') ||
                                    btnText.includes('Подать') || btnText.includes('Выбрать')) {
                                    applyLink = href;
                                    break;
                                } else if (btnText.includes('Подробнее') || btnText.includes('Узнать') ||
                                          btn.classList.contains('product-card__link') ||
                                          btn.classList.contains('dk-sbol-link')) {
                                    if (!detailsLink) {
                                        detailsLink = href;
                                    }
                                }
                            }

                            // Если ссылка на оформление не найдена, берем первую доступную
                            if (!applyLink && allButtons.length > 0) {
                                applyLink = allButtons[0].getAttribute('href') || allButtons[0].href;
                            }
                        }

                        // Оставляем ссылки как есть, нормализация будет в Python коде

                        cards.push({
                            title: title,
                            description: description,
                            features: uniqueFeatures.length > 0 ? uniqueFeatures : null,
                            badge: null,
                            apply_link: applyLink,
                            details_link: detailsLink
                        });
                    } catch (e) {
                        console.error('Ошибка при извлечении карты:', e);
                        continue;
                    }
                }

                return cards;
                """
            )

            # Проверяем, что получили данные
            if not card_data_list:
                print("JavaScript вернул пустой список карт")
                card_data_list = []

            print(f"JavaScript вернул {len(card_data_list)} элементов (до фильтрации по title)")

            # Выводим первые несколько элементов для отладки
            if len(card_data_list) > 0:
                print("Примеры данных из JavaScript (первые 3):")
                for i, card_dict in enumerate(card_data_list[:3], 1):
                    print(f"  Элемент {i}:")
                    print(f"    title: {card_dict.get('title', 'N/A')}")
                    print(f"    description: {card_dict.get('description', 'N/A')[:50] if card_dict.get('description') else 'N/A'}")
                    print(f"    features: {len(card_dict.get('features', [])) if card_dict.get('features') else 0}")

            # Нормализуем ссылки
            normalized_cards = []
            for card_dict in card_data_list:
                if card_dict and card_dict.get("title"):
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
                        else:
                            # Для якорных ссылок (#order) добавляем полный URL
                            card_info["apply_link"] = f"https://www.sberbank.ru/ru/person/bank_cards/credit_cards{card_info['apply_link']}"
                    if card_info["details_link"] and not card_info["details_link"].startswith("http"):
                        if not card_info["details_link"].startswith("#"):
                            card_info["details_link"] = f"https://www.sberbank.ru{card_info['details_link']}"
                        else:
                            card_info["details_link"] = f"https://www.sberbank.ru/ru/person/bank_cards/credit_cards{card_info['details_link']}"
                    normalized_cards.append(card_info)

            cards.extend(normalized_cards)
            print(f"Найдено кредитных карт (после фильтрации): {len(normalized_cards)}")

            # Если карты не найдены, пробуем альтернативный метод
            if len(normalized_cards) == 0:
                print("Основной метод не нашел карты, пробую альтернативный метод...")
                try:
                    # Альтернативный метод - ищем все заголовки и строим карты вокруг них
                    alternative_cards_data = await loop.run_in_executor(
                        None,
                        driver.execute_script,
                        """
                        const cards = [];
                        const catalog = document.querySelector('.product-catalog__product-cards, .product-catalog');

                        if (!catalog) {
                            console.log('Каталог не найден, ищем во всем документе');
                        }

                        const searchContainer = catalog || document.body;

                        // Ищем все элементы с заголовками, которые могут быть картами
                        const headings = searchContainer.querySelectorAll('h2.product-card__heading, .product-card__heading, h2[class*="heading"]');
                        console.log(`Найдено заголовков: ${headings.length}`);

                        for (const heading of headings) {
                            // Находим родительскую карточку
                            let card = heading.closest('.product-card');
                            if (!card) {
                                // Если нет .product-card, пробуем найти контейнер карточки по структуре
                                let parent = heading.parentElement;
                                let depth = 0;
                                while (parent && depth < 5 && !parent.classList.contains('product-card')) {
                                    if (parent.classList.contains('product-card__content') ||
                                        parent.classList.contains('product-card__wrap')) {
                                        card = parent.closest('.product-card') || parent;
                                        break;
                                    }
                                    parent = parent.parentElement;
                                    depth++;
                                }
                            }

                            if (card) {
                                const title = (heading.textContent || '').trim();
                                if (title && title.length > 0) {
                                    // Извлекаем описание
                                    let description = null;
                                    const descEl = card.querySelector('.product-card__description');
                                    if (descEl) {
                                        const descP = descEl.querySelector('p');
                                        description = descP ? (descP.textContent || '').trim() : (descEl.textContent || '').trim();
                                    }

                                    // Извлекаем factoids
                                    const features = [];
                                    const factoidsContainers = card.querySelectorAll('.product-card__factoids');
                                    for (const factoidsContainer of factoidsContainers) {
                                        const factoids = factoidsContainer.querySelectorAll('.factoid');
                                        for (const factoid of factoids) {
                                            const factoidHeading = factoid.querySelector('h3.dk-sbol-heading');
                                            if (factoidHeading) {
                                                const value = (factoidHeading.textContent || '').trim();
                                                let label = null;
                                                const factoidTooltip = factoid.querySelector('.factoid__tooltip .dk-sbol-text p, .factoid__tooltip .dk-sbol-text span, .factoid__tooltip .dk-sbol-text');
                                                const factoidDesc = factoid.querySelector('.factoid__description .dk-sbol-text p, .factoid__description .dk-sbol-text span, .factoid__description .dk-sbol-text');

                                                if (factoidTooltip) {
                                                    label = (factoidTooltip.textContent || '').trim();
                                                } else if (factoidDesc) {
                                                    label = (factoidDesc.textContent || '').trim();
                                                    if (label && label.includes(value)) {
                                                        label = label.replace(value, '').trim();
                                                    }
                                                }

                                                if (value) {
                                                    features.push({ value: value, label: label || value });
                                                }
                                            }
                                        }
                                    }

                                    // Убираем дубликаты
                                    const uniqueFeatures = [];
                                    const seenValues = new Set();
                                    for (const feature of features) {
                                        if (!seenValues.has(feature.value)) {
                                            seenValues.add(feature.value);
                                            uniqueFeatures.push(feature);
                                        }
                                    }

                                    // Извлекаем ссылки
                                    let applyLink = null;
                                    let detailsLink = null;
                                    const buttonsContainer = card.querySelector('.product-card__buttons');
                                    if (buttonsContainer) {
                                        const allButtons = buttonsContainer.querySelectorAll('a');
                                        for (const btn of allButtons) {
                                            const btnText = (btn.textContent || '').trim();
                                            const testId = btn.getAttribute('data-test-id');
                                            const href = btn.getAttribute('href') || btn.href;

                                            if (testId === 'Button-primary-md' || btnText.includes('Оформить') ||
                                                btnText.includes('Подать') || btnText.includes('Выбрать')) {
                                                applyLink = href;
                                                break;
                                            } else if (btnText.includes('Подробнее') || btnText.includes('Узнать') ||
                                                      btn.classList.contains('product-card__link') ||
                                                      btn.classList.contains('dk-sbol-link')) {
                                                if (!detailsLink) {
                                                    detailsLink = href;
                                                }
                                            }
                                        }

                                        if (!applyLink && allButtons.length > 0) {
                                            applyLink = allButtons[0].getAttribute('href') || allButtons[0].href;
                                        }
                                    }

                                    cards.push({
                                        title: title,
                                        description: description,
                                        features: uniqueFeatures.length > 0 ? uniqueFeatures : null,
                                        badge: null,
                                        apply_link: applyLink,
                                        details_link: detailsLink
                                    });
                                }
                            }
                        }

                        return cards;
                        """
                    )

                    if alternative_cards_data and len(alternative_cards_data) > 0:
                        print(f"Альтернативный метод нашел {len(alternative_cards_data)} карт")
                        # Нормализуем ссылки для альтернативных карт
                        for card_dict in alternative_cards_data:
                            if card_dict.get("apply_link") and not card_dict.get("apply_link", "").startswith("http"):
                                if not card_dict["apply_link"].startswith("#"):
                                    card_dict["apply_link"] = f"https://www.sberbank.ru{card_dict['apply_link']}"
                                else:
                                    card_dict["apply_link"] = f"https://www.sberbank.ru/ru/person/bank_cards/credit_cards{card_dict['apply_link']}"
                            if card_dict.get("details_link") and not card_dict.get("details_link", "").startswith("http"):
                                if not card_dict["details_link"].startswith("#"):
                                    card_dict["details_link"] = f"https://www.sberbank.ru{card_dict['details_link']}"
                                else:
                                    card_dict["details_link"] = f"https://www.sberbank.ru/ru/person/bank_cards/credit_cards{card_dict['details_link']}"

                        normalized_cards.extend(alternative_cards_data)
                        cards.extend(alternative_cards_data)
                except Exception as alt_e:
                    print(f"Ошибка при альтернативном извлечении: {alt_e}")
                    traceback.print_exc()

        except Exception as e:
            print(f"Ошибка при извлечении карт: {e}")
            traceback.print_exc()

        # Если карты не найдены, добавляем отладочную информацию
        if len(cards) == 0:
            print("Карты не найдены. Попытка альтернативного извлечения данных...")
            debug_info = await loop.run_in_executor(
                None,
                driver.execute_script,
                """
                const info = {
                    totalCardWraps: document.querySelectorAll('.product-card__wrap').length,
                    totalProductCards: document.querySelectorAll('.product-card').length,
                    hasProductCatalog: !!document.querySelector('.product-catalog__product-cards'),
                    sampleHeadings: []
                };

                // Берем первые 5 заголовков для отладки
                const headings = document.querySelectorAll('.product-card__heading');
                for (let i = 0; i < Math.min(5, headings.length); i++) {
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
            print(f"  Есть блок product-catalog__product-cards: {debug_info.get('hasProductCatalog', False)}")
            print(f"  Примеры заголовков (первые 5):")
            for i, heading in enumerate(debug_info.get('sampleHeadings', [])[:5], 1):
                print(f"    {i}. {heading[:100]}{'...' if len(heading) > 100 else ''}")

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
