"""
Парсер рейтингов банков с сайта Banki.ru.

Парсит таблицу рейтингов банков по различным показателям
с поддержкой пагинации и извлечения данных со всех страниц.
"""

import asyncio
import re
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
from typing import Any
import traceback
from playwright.async_api import Page

from .base import BaseParser


class BankiRatingsParser(BaseParser):
    """
    Парсер рейтингов банков с сайта Banki.ru.

    Парсит таблицу рейтингов с информацией о:
    - Месте в рейтинге (с изменением +/-)
    - Названии банка
    - Номере лицензии и регионе
    - Показателях по двум датам
    - Изменениях в абсолютных значениях и процентах

    Поддерживает автоматический парсинг всех страниц рейтинга.
    """

    async def parse_page(self, url: str) -> dict[str, Any]:
        """
        Парсинг страницы с рейтингами банков Banki.ru.

        Поддерживает автоматический парсинг всех страниц рейтинга.

        Args:
            url: URL страницы рейтингов (может содержать параметр PAGEN_1)

        Returns:
            Словарь с извлеченными данными о рейтингах банков
        """
        page = self.page

        # Убеждаемся, что viewport десктопный
        await page.set_viewport_size({"width": 1920, "height": 1080})

        # Устанавливаем десктопный user agent
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

        # Нормализуем URL: убираем параметр PAGEN_1, если есть, и добавляем необходимые параметры
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query, keep_blank_values=True)

        # Убираем PAGEN_1
        if 'PAGEN_1' in query_params:
            del query_params['PAGEN_1']

        # Добавляем обязательные параметры, если их нет
        if 'sort_param' not in query_params:
            query_params['sort_param'] = ['bankname']
        if 'date1' not in query_params:
            query_params['date1'] = ['2025-12-01']
        if 'date2' not in query_params:
            query_params['date2'] = ['2025-11-01']

        # Формируем URL первой страницы (без PAGEN_1)
        query_string = urlencode(query_params, doseq=True)
        first_page_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, query_string, parsed_url.fragment))

        # Переход на первую страницу
        await page.goto(first_page_url, wait_until="domcontentloaded")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_load_state("networkidle")

        await self.random_delay(1.0, 2.0)

        # Ожидание появления таблицы
        try:
            await page.wait_for_selector('table[data-test="rating-table"]', timeout=self._timeout_to_ms(10.0))
            print("Таблица рейтингов найдена")
        except Exception:
            print("Таблица рейтингов не найдена на странице")

        # Прокрутка для загрузки динамических элементов (включая пагинацию)
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.random_delay(1.0, 1.5)
            await page.evaluate("window.scrollTo(0, 0)")
            await self.random_delay(0.5, 1.0)
        except Exception:
            pass

        # Ожидание загрузки пагинации (если она динамическая)
        try:
            await page.wait_for_selector('.ui-pagination', timeout=self._timeout_to_ms(5.0))
            print("Пагинация найдена")

            # Дополнительное ожидание загрузки описания пагинации
            await self.random_delay(0.5, 1.0)

            # Дополнительная проверка наличия описания пагинации
            pagination_desc_check = await page.locator('.ui-pagination__description').count()
            if pagination_desc_check > 0:
                desc_text = await page.locator('.ui-pagination__description').first.text_content()
                print(f"  Описание пагинации: '{desc_text}'")

                # Пробуем извлечь информацию напрямую для проверки
                match_total = re.search(r'из\s+(\d+)', desc_text)
                if match_total:
                    direct_total_items = int(match_total.group(1))
                    print(f"  Напрямую извлечено total_items из описания: {direct_total_items}")
            else:
                print("  Описание пагинации не найдено, пробуем альтернативные методы...")
                # Пробуем найти пагинацию через альтернативные селекторы
                alt_pagination = await page.locator('.ui-pagination__description, .pagination__description, [class*="pagination"] [class*="description"]').all()
                if alt_pagination:
                    print(f"  Найдено альтернативных элементов пагинации: {len(alt_pagination)}")
                    for i, elem in enumerate(alt_pagination):
                        try:
                            text = await elem.text_content()
                            print(f"    Элемент {i+1}: '{text}'")
                        except Exception:
                            pass
        except Exception as e:
            print(f"Пагинация не найдена или ошибка при поиске: {e}")
            print("  Пробуем продолжить с одной страницей...")

        # Извлекаем информацию о пагинации
        pagination_info = await self._get_pagination_info(page)
        total_pages = pagination_info.get('total_pages', 1)
        total_items = pagination_info.get('total_items', 0)
        pagination_description = pagination_info.get('description', '')

        print(f"\n{'='*60}")
        print(f"ИНФОРМАЦИЯ О ПАГИНАЦИИ (первичная):")
        print(f"  Страниц: {total_pages}")
        print(f"  Элементов: {total_items}")
        print(f"  Описание: {pagination_description}")
        print(f"{'='*60}\n")

        # КРИТИЧЕСКАЯ ПРОВЕРКА: если total_items > 0, то ОБЯЗАТЕЛЬНО пересчитываем total_pages
        if total_items > 0:
            # Определяем количество элементов на странице
            items_per_page = 50  # По умолчанию
            if pagination_description:
                range_match = re.search(r'(\d+)[—–-](\d+)', pagination_description)
                if range_match:
                    start = int(range_match.group(1))
                    end = int(range_match.group(2))
                    items_per_page = end - start + 1
                    print(f"  Определено элементов на странице из диапазона: {items_per_page}")

            # Пересчитываем количество страниц на основе total_items
            calculated_pages = (total_items + items_per_page - 1) // items_per_page

            if calculated_pages != total_pages:
                print(f"  ПЕРЕСЧЕТ КОЛИЧЕСТВА СТРАНИЦ:")
                print(f"     Было: {total_pages}")
                print(f"     Стало: {calculated_pages}")
                print(f"     Расчет: {total_items} элементов / {items_per_page} на странице = {calculated_pages} страниц")
                total_pages = calculated_pages
            else:
                print(f"  Количество страниц подтверждено: {total_pages} (из {total_items} элементов, {items_per_page} на странице)")

        # Финальная проверка: убеждаемся, что total_pages не меньше минимально ожидаемого
        if total_items > 0:
            min_expected_pages = (total_items + 49) // 50  # Минимум ожидаемых страниц
            if total_pages < min_expected_pages:
                print(f"  КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: total_pages ({total_pages}) < минимум ({min_expected_pages})")
                total_pages = min_expected_pages
                print(f"     Установлено: {total_pages} страниц")

        print(f"\n{'='*60}")
        print(f"ФИНАЛЬНАЯ ИНФОРМАЦИЯ О ПАГИНАЦИИ:")
        print(f"  Будет обработано страниц: {total_pages}")
        print(f"  Всего элементов: {total_items}")
        print(f"{'='*60}\n")

        # Извлекаем данные со всех страниц
        all_ratings = []

        # ШАГ 1: Сначала парсим первую страницу, чтобы проверить количество элементов
        print(f"\n{'='*60}")
        print(f"ШАГ 1: Парсинг первой страницы...")
        print(f"{'='*60}\n")

        # Прокрутка для загрузки динамических элементов на первой странице
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.random_delay(0.5, 1.0)
            await page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass

        # Ожидание появления таблицы на первой странице
        try:
            await page.wait_for_selector('table[data-test="rating-table"]', timeout=self._timeout_to_ms(10.0))
        except Exception:
            print("Таблица не найдена на первой странице")

        # Парсим первую страницу
        first_page_ratings = await self._extract_ratings_from_page(page)
        first_page_count = len(first_page_ratings)
        all_ratings.extend(first_page_ratings)
        print(f"Первая страница: найдено {first_page_count} банков (всего накоплено: {len(all_ratings)})")

        # КРИТИЧЕСКАЯ ПРОВЕРКА: если total_items не был определен, пробуем извлечь его еще раз
        # после парсинга первой страницы (возможно, пагинация загрузилась динамически)
        if total_items == 0:
            print(f"\ntotal_items = 0 после первичного извлечения, пробуем извлечь еще раз...")
            try:
                # Пробуем извлечь total_items напрямую через JavaScript
                pagination_retry = await page.evaluate("""
                    () => {
                        const desc = document.querySelector('.ui-pagination__description');
                        if (!desc) return null;
                        const text = desc.textContent || '';
                        const match = text.match(/из\\s+(\\d+)/);
                        if (match) {
                            return {
                                totalItems: parseInt(match[1]),
                                description: text
                            };
                        }
                        return null;
                    }
                """)

                if pagination_retry and pagination_retry.get('totalItems'):
                    total_items = pagination_retry['totalItems']
                    pagination_description = pagination_retry.get('description', pagination_description)
                    print(f"  Извлечено total_items = {total_items} (из описания: '{pagination_description}')")
                else:
                    print(f"  Не удалось извлечь total_items повторно")
            except Exception as e:
                print(f"  Ошибка при повторном извлечении total_items: {e}")

        # КРИТИЧЕСКАЯ ПРОВЕРКА: если на первой странице 50 элементов, но total_pages = 1,
        # ОБЯЗАТЕЛЬНО переопределяем total_pages ДО начала цикла по остальным страницам
        items_per_page_actual = first_page_count if first_page_count > 0 else 50

        if first_page_count >= 50:
            print(f"\nВНИМАНИЕ: На первой странице найдено {first_page_count} банков!")

            if total_pages == 1:
                print(f"   total_pages = 1, но найдено {first_page_count} элементов - ОБЯЗАТЕЛЬНО переопределяем...")

                if total_items > 0:
                    recalculated = (total_items + items_per_page_actual - 1) // items_per_page_actual
                    total_pages = recalculated
                    print(f"   Пересчитано: total_pages = {total_pages} (из {total_items} элементов, {items_per_page_actual} на странице)")
                else:
                    # Если total_items неизвестен, но на странице 50 элементов,
                    # пробуем извлечь total_items из пагинации еще раз
                    print(f"   total_items неизвестен, пробуем извлечь из пагинации еще раз...")

                    # Пробуем извлечь total_items из пагинации напрямую через JavaScript
                    try:
                        pagination_info_retry = await page.evaluate("""
                            () => {
                                const desc = document.querySelector('.ui-pagination__description');
                                if (!desc) return null;
                                const text = desc.textContent || '';
                                const match = text.match(/из\\s+(\\d+)/);
                                if (match) {
                                    return parseInt(match[1]);
                                }
                                return null;
                            }
                        """)

                        if pagination_info_retry and pagination_info_retry > 0:
                            total_items = pagination_info_retry
                            recalculated = (total_items + items_per_page_actual - 1) // items_per_page_actual
                            total_pages = recalculated
                            print(f"   Извлечено total_items = {total_items}, пересчитано: total_pages = {total_pages}")
                        else:
                            # Если все еще неизвестен, используем оценку
                            total_pages = 7  # Оценка: 7 страниц
                            print(f"   total_items все еще неизвестен, установлено: total_pages = {total_pages} (оценка)")
                    except Exception as e:
                        print(f"   Ошибка при повторном извлечении total_items: {e}")
                        total_pages = 7  # Оценка
                        print(f"   Установлено: total_pages = {total_pages} (оценка)")
            else:
                print(f"   total_pages = {total_pages} (уже определен правильно)")

        # Финальная проверка: убеждаемся, что total_pages корректный на основе total_items
        if total_items > 0:
            min_expected = (total_items + items_per_page_actual - 1) // items_per_page_actual
            if total_pages < min_expected:
                print(f"\nКРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: total_pages ({total_pages}) < минимум ({min_expected})")
                total_pages = min_expected
                print(f"   Установлено: total_pages = {total_pages}")

        # КРИТИЧЕСКАЯ ПРОВЕРКА: если на первой странице найдено 50+ элементов,
        # ОБЯЗАТЕЛЬНО устанавливаем total_pages >= 7 (независимо от других условий)
        if first_page_count >= 50:
            if total_pages < 7:
                print(f"\nКРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ:")
                print(f"   На первой странице найдено {first_page_count} банков")
                print(f"   Это означает, что есть еще страницы!")
                print(f"   total_pages был {total_pages}, устанавливаем минимум: total_pages = 7")
                total_pages = 7
            elif total_items > 0 and total_pages < (total_items + items_per_page_actual - 1) // items_per_page_actual:
                # Если total_items известен, используем его для более точного расчета
                recalculated_final = (total_items + items_per_page_actual - 1) // items_per_page_actual
                if recalculated_final > total_pages:
                    print(f"\nФИНАЛЬНЫЙ ПЕРЕСЧЕТ:")
                    print(f"   На основе total_items = {total_items} и items_per_page = {items_per_page_actual}")
                    print(f"   Пересчитываем: total_pages = {total_pages} -> {recalculated_final}")
                    total_pages = recalculated_final

        # Убеждаемся, что total_pages >= 1
        if total_pages < 1:
            total_pages = 1
            print("КРИТИЧЕСКАЯ ОШИБКА: Количество страниц было < 1, установлено в 1")

        print(f"\n{'='*60}")
        print(f"ФИНАЛЬНОЕ РЕШЕНИЕ О КОЛИЧЕСТВЕ СТРАНИЦ:")
        print(f"  total_pages = {total_pages}")
        print(f"  total_items = {total_items}")
        print(f"  Элементов на первой странице = {first_page_count}")
        print(f"  Обработано страниц: 1/{total_pages} (первая)")
        print(f"  Осталось страниц: {total_pages - 1} (со 2-й по {total_pages}-ю)")
        print(f"{'='*60}\n")

        # ШАГ 2: Парсим остальные страницы (со 2-й до total_pages)
        # Используем цикл for с уже определенным total_pages
        # Если total_pages = 1, то range(2, 2) будет пустым, и цикл не выполнится (что правильно)
        remaining_pages = total_pages - 1  # Количество оставшихся страниц (первая уже обработана)
        pages_to_parse = list(range(2, total_pages + 1))  # Список страниц для парсинга

        if remaining_pages > 0:
            print(f"  Будет обработано еще {remaining_pages} страниц (со 2-й по {total_pages}-ю)")
            print(f"  Список страниц для парсинга: {pages_to_parse}\n")
        else:
            print(f"  Остальных страниц нет (total_pages = {total_pages}), парсинг завершен после первой страницы")
            print(f"  Но на первой странице найдено {first_page_count} банков - это подозрительно!")
            print(f"  Возможно, total_pages определен неправильно!\n")

        # Выполняем парсинг остальных страниц
        pages_parsed_count = 0
        for page_num in pages_to_parse:
            pages_parsed_count += 1
            print(f"\n{'─'*60}")
            print(f"ПАРСИНГ СТРАНИЦЫ {page_num} из {total_pages} (страница {pages_parsed_count}/{remaining_pages} из оставшихся)...")
            print(f"{'─'*60}")

            # Формируем URL для конкретной страницы
            parsed_url = urlparse(first_page_url)
            query_params = parse_qs(parsed_url.query, keep_blank_values=True)
            query_params['PAGEN_1'] = [str(page_num)]

            query_string = urlencode(query_params, doseq=True)
            page_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, query_string, parsed_url.fragment))

            print(f"  Переход на страницу {page_num}: {page_url}")
            await page.goto(page_url, wait_until="domcontentloaded")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_load_state("networkidle")
            await self.random_delay(1.0, 2.0)

            # Прокрутка для загрузки динамических элементов
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self.random_delay(0.5, 1.0)
                await page.evaluate("window.scrollTo(0, 0)")
            except Exception:
                pass

            # Ожидание появления таблицы
            try:
                await page.wait_for_selector('table[data-test="rating-table"]', timeout=self._timeout_to_ms(10.0))
            except Exception:
                print(f"Таблица не найдена на странице {page_num}, пропускаем")
                continue

            # Извлекаем данные со страницы
            page_ratings = await self._extract_ratings_from_page(page)

            if not page_ratings:
                print(f"  Страница {page_num} пуста (не извлечено ни одного банка)")
            else:
                all_ratings.extend(page_ratings)
                print(f"  Найдено банков на странице {page_num}: {len(page_ratings)} (всего накоплено: {len(all_ratings)})")

            # Задержка между страницами (кроме последней)
            if page_num < total_pages:
                await self.random_delay(1.0, 2.0)

        print(f"\n{'='*60}")
        print(f"ШАГ 2 ЗАВЕРШЕН:")
        print(f"  Обработано дополнительных страниц: {pages_parsed_count} из {remaining_pages}")
        print(f"  Всего страниц обработано: 1 (первая) + {pages_parsed_count} (остальные) = {1 + pages_parsed_count}")
        print(f"  Всего банков накоплено: {len(all_ratings)}")
        print(f"{'='*60}\n")

        # Извлекаем метаданные (даты, показатели) с первой страницы
        # Переходим на первую страницу для извлечения метаданных
        if total_pages > 1:
            await page.goto(first_page_url, wait_until="domcontentloaded")
            await page.wait_for_load_state("domcontentloaded")
            await self.random_delay(0.5, 1.0)

        metadata = await self._extract_metadata(page)

        # Сортируем данные по месту в рейтинге от меньшего к большему
        all_ratings_sorted = sorted(all_ratings, key=lambda x: (x.get('place', 999999) or 999999))

        print(f"\nПарсинг завершен: всего извлечено банков: {len(all_ratings_sorted)} из {total_pages} страниц")
        print(f"  Диапазон мест в рейтинге: {min(r.get('place', 0) or 0 for r in all_ratings_sorted)} - {max(r.get('place', 0) or 0 for r in all_ratings_sorted)}")

        return {
            "url": first_page_url,
            "title": await page.title(),
            "total_pages": total_pages,
            "total_banks": len(all_ratings_sorted),
            "metadata": metadata,
            "ratings": all_ratings_sorted,
        }

    async def _get_pagination_info(self, page: Page) -> dict[str, Any]:
        """
        Извлечь информацию о пагинации.

        Args:
            page: Страница Playwright

        Returns:
            Словарь с информацией о пагинации (total_pages, total_items)
        """
        total_items = 0
        total_pages = 1
        pagination_description = None

        try:
            # Ищем пагинацию - пробуем разные селекторы
            pagination_desc_locator = page.locator('.ui-pagination__description').first
            if await pagination_desc_locator.count() > 0:
                pagination_description = await pagination_desc_locator.text_content()

                # Извлекаем общее количество элементов из текста типа "51—100 из 325" или "1—50 из 325"
                if pagination_description:
                    pagination_description = pagination_description.strip()
                    print(f"  Текст описания пагинации: '{pagination_description}'")

                    # Парсим формат "51—100 из 325" или "1—50 из 325" или "51-100 из 325"
                    # Пробуем разные варианты регулярных выражений
                    match_total = re.search(r'из\s+(\d+)', pagination_description)
                    if not match_total:
                        # Пробуем альтернативный формат (без пробела)
                        match_total = re.search(r'из(\d+)', pagination_description)
                    if not match_total:
                        # Пробуем еще один формат (кириллическая буква "и" или "из")
                        match_total = re.search(r'[ииз]\s*(\d+)', pagination_description)

                    if match_total:
                        total_items = int(match_total.group(1))
                        print(f"  Извлечено общее количество элементов: {total_items}")
                    else:
                        print(f"  Не удалось извлечь total_items из текста: '{pagination_description}'")
                        # Пробуем извлечь напрямую число в конце строки после "из"
                        parts = pagination_description.split('из')
                        if len(parts) > 1:
                            last_part = parts[-1].strip()
                            numbers = re.findall(r'\d+', last_part)
                            if numbers:
                                total_items = int(numbers[0])
                                print(f"  Извлечено total_items альтернативным способом: {total_items}")

                        # Извлекаем диапазон для определения количества элементов на странице
                        range_match = re.search(r'(\d+)[—–-](\d+)', pagination_description)
                        items_per_page = 50  # По умолчанию
                        if range_match:
                            start = int(range_match.group(1))
                            end = int(range_match.group(2))
                            items_per_page = end - start + 1
                            print(f"  Извлечен диапазон: {start}—{end} (элементов на странице: {items_per_page})")
                        else:
                            print(f"  Не удалось извлечь диапазон, используется значение по умолчанию: {items_per_page}")

                        # Рассчитываем общее количество страниц на основе общего количества элементов
                        if total_items > 0 and items_per_page > 0:
                            calculated_total_pages = (total_items + items_per_page - 1) // items_per_page
                            total_pages = calculated_total_pages
                            print(f"  Рассчитано страниц: {total_pages} (из {total_items} элементов, {items_per_page} на странице)")
                        else:
                            print(f"  Невозможно рассчитать страницы: total_items={total_items}, items_per_page={items_per_page}")
                else:
                    print(f"  Не удалось извлечь общее количество элементов из пагинации: '{pagination_description}'")
                    print(f"     Пробую альтернативные методы...")
            else:
                print(f"  Описание пагинации пустое")

            # Также пробуем найти все ссылки на страницы в пагинации для проверки
            # Сначала пробуем через data-page-number
            page_links = await page.locator('.ui-pagination__item--number a[data-page-number]').all()
            page_numbers = []

            if page_links:
                for link in page_links:
                    try:
                        page_num = await link.get_attribute('data-page-number')
                        if page_num:
                            page_numbers.append(int(page_num))
                    except Exception:
                        pass

            # Если не нашли через data-page-number, пробуем через текст ссылок
            if not page_numbers:
                text_links = await page.locator('.ui-pagination__item--number a').all()
                for link in text_links:
                    try:
                        page_text = await link.text_content()
                        if page_text and page_text.strip().isdigit():
                            page_numbers.append(int(page_text.strip()))
                    except Exception:
                        pass

            if page_numbers:
                max_visible_page = max(page_numbers)
                # Используем максимальную видимую страницу только если total_pages еще не определен
                # или если она больше уже определенного значения
                if total_pages == 1 or max_visible_page > total_pages:
                    # Но лучше использовать расчет на основе total_items, если он известен
                    if total_items == 0:
                        # Если total_items неизвестен, используем видимую страницу как минимальную оценку
                        total_pages = max_visible_page
                        print(f"Найдено страниц через видимые ссылки пагинации (минимальная оценка): {total_pages}")
                    else:
                        # total_pages уже рассчитан на основе total_items, это более точное значение
                        print(f"Максимальная видимая страница: {max_visible_page}, рассчитано страниц: {total_pages}")

            # Всегда пробуем получить информацию из JavaScript для проверки и уточнения
            pagination_info_js = await page.evaluate("""
                () => {
                    const pagination = document.querySelector('.ui-pagination');
                    if (!pagination) return null;

                    const description = pagination.querySelector('.ui-pagination__description');
                    const descriptionText = description ? description.textContent : '';

                    // Извлекаем общее количество элементов из текста "51—100 из 325"
                    let totalItems = 0;
                    const totalMatch = descriptionText.match(/из\\s+(\\d+)/);
                    if (totalMatch) {
                        totalItems = parseInt(totalMatch[1]);
                    }

                    // Извлекаем диапазон для определения элементов на странице
                    let itemsPerPage = 50; // По умолчанию
                    const rangeMatch = descriptionText.match(/(\\d+)[—–-](\\d+)/);
                    if (rangeMatch) {
                        const start = parseInt(rangeMatch[1]);
                        const end = parseInt(rangeMatch[2]);
                        itemsPerPage = end - start + 1;
                    }

                    // Извлекаем номера всех видимых страниц через data-page-number
                    const pageLinks = pagination.querySelectorAll('.ui-pagination__item--number a[data-page-number]');
                    const pageNumbers = [];
                    for (const link of pageLinks) {
                        const pageNum = parseInt(link.getAttribute('data-page-number'));
                        if (!isNaN(pageNum)) {
                            pageNumbers.push(pageNum);
                        }
                    }

                    const maxVisiblePage = pageNumbers.length > 0 ? Math.max(...pageNumbers) : 1;

                    // Рассчитываем общее количество страниц на основе totalItems
                    let calculatedPages = maxVisiblePage;
                    if (totalItems > 0 && itemsPerPage > 0) {
                        calculatedPages = Math.ceil(totalItems / itemsPerPage);
                    }

                    return {
                        totalItems: totalItems,
                        maxVisiblePage: maxVisiblePage,
                        calculatedPages: Math.max(maxVisiblePage, calculatedPages),
                        itemsPerPage: itemsPerPage,
                        description: descriptionText,
                        pageNumbers: pageNumbers
                    };
                }
            """)

            if pagination_info_js:
                js_total_items = pagination_info_js.get('totalItems', 0)
                js_calculated_pages = pagination_info_js.get('calculatedPages', 1)
                js_max_visible = pagination_info_js.get('maxVisiblePage', 1)
                js_items_per_page = pagination_info_js.get('itemsPerPage', 50)
                js_page_numbers = pagination_info_js.get('pageNumbers', [])

                # Обновляем total_items, если JavaScript вернул значение
                if js_total_items > 0:
                    total_items = js_total_items
                    print(f"JavaScript извлек total_items: {total_items}")

                # Обновляем total_pages на основе JavaScript-расчета (более надежно)
                if js_calculated_pages > 0:
                    total_pages = js_calculated_pages
                    print(f"JavaScript рассчитал количество страниц: {total_pages} (из {js_total_items} элементов, {js_items_per_page} на странице, видимых страниц: {js_max_visible}, номера: {js_page_numbers})")
                elif js_max_visible > total_pages:
                    # Если расчет не сработал, используем максимальную видимую страницу
                    total_pages = js_max_visible
                    print(f"JavaScript нашел максимальную видимую страницу: {total_pages}")

                # Если total_items известен, пересчитываем total_pages для надежности
                if js_total_items > 0 and js_items_per_page > 0:
                    recalculated_pages = (js_total_items + js_items_per_page - 1) // js_items_per_page
                    if recalculated_pages > total_pages:
                        total_pages = recalculated_pages
                        print(f"Пересчитано количество страниц: {total_pages} (из {js_total_items} элементов, {js_items_per_page} на странице)")

                if not pagination_description:
                    pagination_description = pagination_info_js.get('description')

            # КРИТИЧЕСКАЯ ПРОВЕРКА: финальный пересчет total_pages на основе total_items
            # Это гарантирует, что даже если предыдущие методы не сработали, мы правильно рассчитаем страницы
            if total_items > 0:
                items_per_page_final = 50  # По умолчанию
                if pagination_description:
                    range_match_final = re.search(r'(\d+)[—–-](\d+)', pagination_description)
                    if range_match_final:
                        start = int(range_match_final.group(1))
                        end = int(range_match_final.group(2))
                        items_per_page_final = end - start + 1

                # ВСЕГДА пересчитываем total_pages на основе total_items
                calculated_pages_final = (total_items + items_per_page_final - 1) // items_per_page_final

                if calculated_pages_final != total_pages:
                    print(f"\nФИНАЛЬНЫЙ ПЕРЕСЧЕТ total_pages:")
                    print(f"   Было: {total_pages}")
                    print(f"   Стало: {calculated_pages_final}")
                    print(f"   Расчет: {total_items} элементов ÷ {items_per_page_final} на странице = {calculated_pages_final} страниц")
                    total_pages = calculated_pages_final
                else:
                    print(f"\ntotal_pages подтвержден: {total_pages} (из {total_items} элементов, {items_per_page_final} на странице)")
            else:
                print(f"\ntotal_items = 0, невозможно точно определить количество страниц")

            print(f"\n[PAGINATION] ИТОГОВЫЕ ЗНАЧЕНИЯ:")
            print(f"   total_pages = {total_pages}")
            print(f"   total_items = {total_items}")
            print(f"   description = {pagination_description}")

            return {
                "total_pages": total_pages,
                "total_items": total_items,
                "description": pagination_description
            }
        except Exception as e:
            print(f"Ошибка при извлечении информации о пагинации: {e}")
            traceback.print_exc()
            return {"total_pages": 1, "total_items": 0}

    async def _extract_metadata(self, page: Page) -> dict[str, Any]:
        """
        Извлечь метаданные о рейтинге (даты, показатели).

        Args:
            page: Страница Playwright

        Returns:
            Словарь с метаданными
        """
        metadata = {}

        try:
            # Извлекаем выбранные даты из селектов
            date1_select = page.locator('select[name="date1"]').first
            date2_select = page.locator('select[name="date2"]').first

            if await date1_select.count() > 0:
                date1_value = await date1_select.input_value()
                date1_text = await date1_select.locator(f'option[value="{date1_value}"]').first.text_content()
                metadata['date1'] = {
                    'value': date1_value,
                    'display': date1_text.strip() if date1_text else None
                }

            if await date2_select.count() > 0:
                date2_value = await date2_select.input_value()
                date2_text = await date2_select.locator(f'option[value="{date2_value}"]').first.text_content()
                metadata['date2'] = {
                    'value': date2_value,
                    'display': date2_text.strip() if date2_text else None
                }

            # Извлекаем название показателя (ищем во втором блоке rating-parameters__item)
            # Используем JavaScript для более надежного извлечения
            metadata_js = await page.evaluate("""
                () => {
                    const result = {};

                    // Извлекаем показатель (второй блок rating-parameters__item)
                    const indicatorItems = document.querySelectorAll('.rating-parameters__item');
                    if (indicatorItems.length >= 2) {
                        const indicatorB = indicatorItems[1].querySelector('h3 b');
                        if (indicatorB) {
                            result.indicator = indicatorB.textContent.trim();
                        }

                        // Извлекаем регион (первый блок)
                        const regionH3 = indicatorItems[0].querySelector('h3');
                        if (regionH3) {
                            let regionText = regionH3.textContent.trim();
                            // Убираем количество в скобках (например, "все регионы(353)")
                            regionText = regionText.replace(/\\s*\\(\\d+\\)\\s*$/, '');
                            result.region = regionText;
                        }
                    }

                    return result;
                }
            """)

            if metadata_js:
                if metadata_js.get('indicator'):
                    metadata['indicator'] = metadata_js['indicator']
                if metadata_js.get('region'):
                    metadata['region'] = metadata_js['region']

        except Exception as e:
            print(f"Ошибка при извлечении метаданных: {e}")

        return metadata

    async def _extract_ratings_from_page(self, page: Page) -> list[dict[str, Any]]:
        """
        Извлечь данные о рейтингах со страницы.

        Args:
            page: Страница Playwright

        Returns:
            Список словарей с данными о рейтингах банков
        """
        ratings = []

        try:
            # Ищем все строки таблицы с data-test="rating-table-item"
            rows = page.locator('tr[data-test="rating-table-item"]')
            rows_count = await rows.count()

            if rows_count == 0:
                # Пробуем альтернативный селектор
                print("Строки таблицы не найдены через data-test, пробуем альтернативный селектор...")
                rows = page.locator('table[data-test="rating-table"] tbody tr, table.rating-table tbody tr')
                rows_count = await rows.count()

                if rows_count == 0:
                    print("Строки таблицы не найдены вообще")
                    return ratings
                else:
                    print(f"  Найдено строк через альтернативный селектор: {rows_count}")
            else:
                print(f"  Найдено строк в таблице: {rows_count}")

            for i in range(rows_count):
                try:
                    row = rows.nth(i)

                    # Проверяем, что строка видима
                    if not await row.is_visible():
                        print(f"  Пропущена невидимая строка {i + 1}")
                        continue

                    # Извлекаем место в рейтинге
                    place_cell = row.locator('td').first
                    place = None
                    place_change = None
                    place_change_type = None

                    # Сначала определяем все ячейки строки, чтобы использовать их дальше
                    all_cells = row.locator('td')
                    cells_count = await all_cells.count()

                    try:
                        # Получаем текст ячейки (без HTML тегов)
                        place_text = await place_cell.inner_text()
                        if place_text:
                            place_text = place_text.strip()
                            # Парсим место (например, "223" или "85")
                            place_match = re.match(r'(\d+)', place_text)
                            if place_match:
                                place = int(place_match.group(1))

                        # Получаем HTML для извлечения изменения из <sup>
                        place_html = await place_cell.inner_html()
                        if place_html:
                            # Извлекаем изменение из <sup>
                            sup_match = re.search(r'<sup[^>]*class="([^"]*)"[^>]*>\s*&nbsp;\s*([+-]?\d+)</sup>', place_html)
                            if sup_match:
                                change_class = sup_match.group(1)
                                change_value = sup_match.group(2)
                                place_change = int(change_value.replace('+', ''))

                                if 'color-green' in change_class:
                                    place_change_type = 'up'
                                elif 'color-red' in change_class:
                                    place_change_type = 'down'
                    except Exception as e:
                        print(f"Ошибка при извлечении места в рейтинге для строки {i + 1}: {e}")

                    # Извлекаем название банка - пробуем разные способы
                    bank_name = None
                    bank_link = None

                    # Способ 1: через data-test="rating-bank-name"
                    bank_name_element = row.locator('a[data-test="rating-bank-name"]').first
                    if await bank_name_element.count() > 0:
                        bank_name = await bank_name_element.text_content()
                        bank_link = await bank_name_element.get_attribute('href')
                        if bank_name:
                            bank_name = bank_name.strip()

                    # Способ 2: если не нашли через data-test, пробуем через вторую ячейку td
                    if not bank_name and cells_count >= 2:
                        try:
                            # Вторая ячейка обычно содержит название банка
                            bank_cell = all_cells.nth(1)
                            if await bank_cell.count() > 0:
                                # Пробуем найти ссылку в этой ячейке
                                bank_link_elem = bank_cell.locator('a').first
                                if await bank_link_elem.count() > 0:
                                    bank_name = await bank_link_elem.text_content()
                                    bank_link = await bank_link_elem.get_attribute('href')
                                    if bank_name:
                                        bank_name = bank_name.strip()
                                else:
                                    # Если ссылки нет, берем весь текст ячейки (но исключаем лицензию)
                                    bank_cell_text = await bank_cell.text_content()
                                    if bank_cell_text:
                                        # Берем только первую строку (название банка) до переноса строки или запятой
                                        bank_name = bank_cell_text.split('\n')[0].split(',')[0].strip()
                        except Exception as e:
                            print(f"Ошибка при альтернативном извлечении названия банка для строки {i + 1}: {e}")

                    # Способ 3: если все еще не нашли, пробуем через JavaScript
                    if not bank_name:
                        try:
                            bank_info_js = await row.evaluate("""
                                () => {
                                    const cells = this.querySelectorAll('td');
                                    if (cells.length < 2) return null;

                                    const bankCell = cells[1];
                                    const bankLink = bankCell.querySelector('a[data-test="rating-bank-name"]');
                                    if (bankLink) {
                                        return {
                                            name: bankLink.textContent.trim(),
                                            link: bankLink.getAttribute('href')
                                        };
                                    }

                                    // Пробуем любую ссылку в ячейке
                                    const anyLink = bankCell.querySelector('a');
                                    if (anyLink) {
                                        return {
                                            name: anyLink.textContent.trim(),
                                            link: anyLink.getAttribute('href')
                                        };
                                    }

                                    // Берем текст без ссылки (первая строка)
                                    const text = bankCell.textContent.trim();
                                    const firstLine = text.split('\\n')[0].split(',')[0].trim();
                                    if (firstLine && firstLine.length > 0 && !firstLine.toLowerCase().includes('лицензия')) {
                                        return {
                                            name: firstLine,
                                            link: null
                                        };
                                    }

                                    return null;
                                }
                            """)

                            if bank_info_js and bank_info_js.get('name'):
                                bank_name = bank_info_js['name'].strip()
                                bank_link = bank_info_js.get('link')
                        except Exception as e:
                            print(f"Ошибка при JavaScript извлечении названия банка для строки {i + 1}: {e}")

                    # Извлекаем лицензию и регион - пробуем разные способы
                    license_number = None
                    region = None

                    # Способ 1: через класс .font-size-small.color-gray-burn
                    license_region_element = row.locator('.font-size-small.color-gray-burn').first
                    if await license_region_element.count() > 0:
                        license_region_text = await license_region_element.text_content()
                        if license_region_text:
                            license_region_text = license_region_text.strip()
                            # Парсим "лицензия № 1144, Братск"
                            license_match = re.search(r'лицензия\s*№\s*([^,]+)', license_region_text)
                            if license_match:
                                license_number = license_match.group(1).strip()

                            region_match = re.search(r',\s*(.+)', license_region_text)
                            if region_match:
                                region = region_match.group(1).strip()

                    # Способ 2: если не нашли, пробуем из второй ячейки (там обычно есть лицензия и регион)
                    if not license_number or not region:
                        try:
                            bank_cell = all_cells.nth(1)
                            if await bank_cell.count() > 0:
                                bank_cell_text = await bank_cell.text_content()
                                if bank_cell_text:
                                    # Парсим "лицензия № 1144, Братск" или "лицензия № 1481, Москва"
                                    license_match = re.search(r'лицензия\s*№\s*([^,]+)', bank_cell_text)
                                    if license_match:
                                        license_number = license_match.group(1).strip()

                                    region_match = re.search(r',\s*(.+)', bank_cell_text)
                                    if region_match:
                                        region = region_match.group(1).strip()
                        except Exception as e:
                            print(f"Ошибка при альтернативном извлечении лицензии/региона для строки {i + 1}: {e}")

                    # Значения для показателей (all_cells уже определен выше)
                    value_date1 = None  # Значение для date1
                    value_date2 = None  # Значение для date2
                    change_absolute = None  # Абсолютное изменение
                    change_percent = None  # Изменение в процентах
                    change_type = None  # Тип изменения (increase/decrease)

                    # Структура строки: [место, название+лицензия, date1, date2, изменение (тыс. руб.), изменение (%)]
                    # Индексы: 0 - место, 1 - название, 2 - date1, 3 - date2, 4 - изменение (тыс. руб.), 5 - изменение (%)
                    # Но может быть и другая структура, поэтому проверяем минимальное количество ячеек
                    if cells_count < 4:
                        print(f"  Предупреждение: строка {i + 1} имеет только {cells_count} ячеек, пропускаем")
                        continue

                    # Обрабатываем ячейки с данными - пробуем разные индексы в зависимости от структуры
                    if cells_count >= 6:
                        # Полная структура: место, название, date1, date2, изменение, изменение (%)
                        value_date1_index = 2
                        value_date2_index = 3
                        change_abs_index = 4
                        change_percent_index = 5
                    elif cells_count >= 5:
                        # Структура без date2: место, название, date1, изменение, изменение (%)
                        value_date1_index = 2
                        value_date2_index = None  # Нет date2
                        change_abs_index = 3
                        change_percent_index = 4
                    else:
                        # Минимальная структура: место, название, date1, изменение (%)
                        value_date1_index = 2
                        value_date2_index = None
                        change_abs_index = None
                        change_percent_index = 3 if cells_count >= 4 else None

                    if cells_count >= 4:
                        try:
                            # Извлекаем значение для date1
                            if value_date1_index is not None:
                                cell_date1 = all_cells.nth(value_date1_index)
                                value_date1_text = await cell_date1.text_content()
                                if value_date1_text:
                                    value_date1 = self._parse_number(value_date1_text.strip())

                            # Извлекаем значение для date2 (если есть)
                            if value_date2_index is not None:
                                cell_date2 = all_cells.nth(value_date2_index)
                                value_date2_text = await cell_date2.text_content()
                                if value_date2_text:
                                    value_date2 = self._parse_number(value_date2_text.strip())

                            # Извлекаем абсолютное изменение и изменение в процентах
                            # Пробуем два подхода:
                            # 1. Если есть отдельные ячейки для изменений (change_abs_index и change_percent_index)
                            # 2. Если данные в одной ячейке в формате "+1,250,801 (+0.37%)"

                            # Подход 1: Отдельные ячейки
                            if change_abs_index is not None:
                                cell_change_abs = all_cells.nth(change_abs_index)
                                change_abs_text = await cell_change_abs.text_content()
                                if change_abs_text:
                                    change_abs_text = change_abs_text.strip()
                                    change_absolute = self._parse_number(change_abs_text)
                                    if change_absolute is None and change_abs_text:
                                        # Логируем, если не удалось распарсить
                                        print(f"  Строка {i + 1}: не удалось распарсить абсолютное изменение из '{change_abs_text}' (индекс {change_abs_index})")

                                # Проверяем цвет ячейки абсолютного изменения
                                change_abs_class = await cell_change_abs.get_attribute('class')
                                if change_abs_class:
                                    if 'color-green' in change_abs_class:
                                        change_type = 'increase'
                                    elif 'color-red' in change_abs_class:
                                        change_type = 'decrease'

                            if change_percent_index is not None:
                                cell_change_perc = all_cells.nth(change_percent_index)
                                change_perc_text = await cell_change_perc.text_content()
                                if change_perc_text:
                                    change_perc_text = change_perc_text.strip()
                                    change_percent = self._parse_percent(change_perc_text)
                                    if change_percent is None and change_perc_text:
                                        # Логируем, если не удалось распарсить
                                        print(f"  Строка {i + 1}: не удалось распарсить изменение в % из '{change_perc_text}' (индекс {change_percent_index})")

                                # Если тип изменения не определен по абсолютному изменению, проверяем процентное
                                if not change_type:
                                    change_perc_class = await cell_change_perc.get_attribute('class')
                                    if change_perc_class:
                                        if 'color-green' in change_perc_class:
                                            change_type = 'increase'
                                        elif 'color-red' in change_perc_class:
                                            change_type = 'decrease'

                            # Подход 2: Если данные не извлечены, пробуем найти их в одной ячейке
                            # Формат может быть: "+1,250,801 (+0.37%)" или "+1 250 801 (+0.37%)"
                            if change_absolute is None or change_percent is None:
                                # Пробуем найти ячейку с изменениями, перебирая все ячейки после места и названия
                                # Начинаем с индекса 2 (после места и названия) и идем до конца
                                for cell_idx in range(2, cells_count):
                                    try:
                                        cell = all_cells.nth(cell_idx)
                                        cell_text = await cell.text_content()
                                        if not cell_text:
                                            continue

                                        cell_text = cell_text.strip()

                                        # Пробуем найти формат "+1,250,801 (+0.37%)" или "+1 250 801 (+0.37%)"
                                        # Ищем паттерн: число (с разделителями) и в скобках процент
                                        # Улучшенный паттерн: учитываем различные форматы разделителей
                                        combined_match = re.search(
                                            r'([+-]?[\d\s,]+)\s*\(([+-]?[\d.,]+)%\)',
                                            cell_text
                                        )

                                        if combined_match:
                                            # Нашли комбинированный формат
                                            abs_str = combined_match.group(1).strip()
                                            percent_str = combined_match.group(2).strip()

                                            # Парсим абсолютное изменение
                                            if change_absolute is None:
                                                change_absolute = self._parse_number(abs_str)

                                            # Парсим процентное изменение
                                            if change_percent is None:
                                                change_percent = self._parse_percent(percent_str)

                                            # Определяем тип изменения по знаку
                                            if not change_type:
                                                if abs_str.startswith('+') or (change_absolute and change_absolute > 0):
                                                    change_type = 'increase'
                                                elif abs_str.startswith('-') or (change_absolute and change_absolute < 0):
                                                    change_type = 'decrease'

                                            # Если нашли данные, прекращаем поиск
                                            if change_absolute is not None or change_percent is not None:
                                                if i < 3:  # Логируем для первых 3 строк
                                                    print(f"  Строка {i + 1}: найдены изменения в ячейке {cell_idx} в комбинированном формате: '{cell_text}'")
                                                break

                                        # Дополнительная попытка: ищем изменения в формате без скобок
                                        # Например: "+1,250,801 +0.37%" или "+1 250 801 +0.37%"
                                        if change_absolute is None or change_percent is None:
                                            # Ищем два числа подряд: абсолютное и процентное
                                            two_numbers_match = re.search(
                                                r'([+-]?[\d\s,]+)\s+([+-]?[\d.,]+)%',
                                                cell_text
                                            )
                                            if two_numbers_match:
                                                abs_str = two_numbers_match.group(1).strip()
                                                percent_str = two_numbers_match.group(2).strip()

                                                if change_absolute is None:
                                                    change_absolute = self._parse_number(abs_str)
                                                if change_percent is None:
                                                    change_percent = self._parse_percent(percent_str)

                                                if not change_type:
                                                    if abs_str.startswith('+') or (change_absolute and change_absolute > 0):
                                                        change_type = 'increase'
                                                    elif abs_str.startswith('-') or (change_absolute and change_absolute < 0):
                                                        change_type = 'decrease'

                                                if change_absolute is not None or change_percent is not None:
                                                    if i < 3:
                                                        print(f"  Строка {i + 1}: найдены изменения в ячейке {cell_idx} в формате двух чисел: '{cell_text}'")
                                                    break
                                    except Exception as e:
                                        if i < 3:
                                            print(f"  Строка {i + 1}: ошибка при проверке ячейки {cell_idx}: {e}")

                            # Дополнительная диагностика для первых строк: выводим все ячейки
                            if i < 3:
                                print(f"  Строка {i + 1}: Диагностика ячеек (всего {cells_count}):")
                                for cell_idx in range(min(cells_count, 7)):  # Показываем первые 7 ячеек
                                    try:
                                        cell = all_cells.nth(cell_idx)
                                        cell_text = await cell.text_content()
                                        cell_class = await cell.get_attribute('class')
                                        print(f"    Ячейка {cell_idx}: '{cell_text.strip() if cell_text else '(пусто)'}' (class: {cell_class})")
                                    except Exception as e:
                                        print(f"    Ячейка {cell_idx}: ошибка при извлечении: {e}")
                                print(f"  Строка {i + 1}: Результат извлечения - change_absolute={change_absolute}, change_percent={change_percent}, change_type={change_type}")

                        except Exception as e:
                            print(f"Ошибка при извлечении показателей для строки {i + 1}: {e}")

                    # Создаем запись о рейтинге только если есть название банка и место в рейтинге
                    if bank_name and place is not None:
                        rating_data = {
                            "place": place,
                            "place_change": place_change,
                            "place_change_type": place_change_type,
                            "bank_name": bank_name,
                            "bank_link": self._normalize_url(bank_link) if bank_link else None,
                            "license_number": license_number or "",
                            "region": region or "",
                            "value_date1": value_date1,
                            "value_date2": value_date2,
                            "change_absolute": change_absolute,
                            "change_percent": change_percent,
                            "change_type": change_type,
                        }
                        ratings.append(rating_data)
                    else:
                        # Детальная диагностика пропущенной строки
                        if not bank_name:
                            print(f"Пропущена строка {i + 1}: не найдено название банка (место: {place})")
                            # Пробуем вывести содержимое строки для отладки
                            try:
                                row_text = await row.text_content()
                                print(f"    Содержимое строки: {row_text[:200]}...")
                            except Exception:
                                pass
                        if place is None:
                            print(f"Пропущена строка {i + 1}: не найдено место в рейтинге (банк: {bank_name})")

                except Exception as e:
                    print(f"Ошибка при обработке строки {i + 1}: {e}")
                    continue

        except Exception as e:
            print(f"Ошибка при извлечении рейтингов со страницы: {e}")
            traceback.print_exc()

        print(f"  Итого извлечено рейтингов со страницы: {len(ratings)} из {rows_count} строк")
        return ratings

    def _parse_number(self, text: str) -> float | None:
        """
        Парсинг числа из текста (убирает пробелы-разделители тысяч).

        Args:
            text: Текст с числом

        Returns:
            Числовое значение или None
        """
        if not text:
            return None

        try:
            # Убираем пробелы и другие разделители, заменяем запятую на точку
            cleaned = text.replace(' ', '').replace('\xa0', '').replace(',', '.')
            # Убираем все кроме цифр, точек, минусов и плюсов
            cleaned = re.sub(r'[^\d.\-+]', '', cleaned)

            if cleaned:
                # Обрабатываем знаки +/-
                sign = 1
                if cleaned.startswith('-'):
                    sign = -1
                    cleaned = cleaned[1:]
                elif cleaned.startswith('+'):
                    cleaned = cleaned[1:]

                value = float(cleaned) * sign
                return value
        except Exception:
            pass

        return None

    def _parse_percent(self, text: str) -> float | None:
        """
        Парсинг процента из текста.

        Args:
            text: Текст с процентом (например, "+6,16%" или "-2,86%")

        Returns:
            Числовое значение процента или None
        """
        if not text:
            return None

        try:
            # Убираем знак процента, пробелы, заменяем запятую на точку
            cleaned = text.replace('%', '').replace(' ', '').replace('\xa0', '').replace(',', '.')
            # Убираем все кроме цифр, точек, минусов и плюсов
            cleaned = re.sub(r'[^\d.\-+]', '', cleaned)

            if cleaned:
                sign = 1
                if cleaned.startswith('-'):
                    sign = -1
                    cleaned = cleaned[1:]
                elif cleaned.startswith('+'):
                    cleaned = cleaned[1:]

                value = float(cleaned) * sign
                return value
        except Exception:
            pass

        return None

    def _normalize_url(self, url: str) -> str | None:
        """
        Нормализация URL (добавление домена, если относительный).

        Args:
            url: URL (может быть относительным или абсолютным)

        Returns:
            Полный URL или None, если url пустой
        """
        if not url:
            return None

        if url.startswith('http://') or url.startswith('https://'):
            return url

        if url.startswith('/'):
            return f"https://www.banki.ru{url}"

        return f"https://www.banki.ru/{url}"
