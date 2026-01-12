"""
Парсер данных о ценных бумагах с Московской биржи (MOEX) через ISS API.

Использует MOEX ISS API для получения информации о ценных бумагах банков
и исторических данных о котировках.
"""

from datetime import datetime, timedelta
from typing import Any
from matplotlib import dates as mdates
import httpx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import traceback


class MoexSecuritiesParser:
    """
    Парсер данных о ценных бумагах с Московской биржи.

    Получает информацию о ценных бумагах банков и исторические данные о котировках.
    """

    # Маппинг названий банков
    BANK_NAMES = {
        "1": {"search": "SBER", "display": "Сбер"},
        "2": {"search": "gazprom", "display": "Газпромбанк"},
        "3": {"search": "VTB Bank", "display": "ВТБ"},
        "4": {"search": "АЛЬФА-БАНК", "display": "Альфа-банк"},
        "5": {"search": "TCS Bank", "display": "Т-Банк"},
    }

    # Маппинг типов ценных бумаг (ключ - русское название, значение - тип в API MOEX)
    # Используются реальные типы из MOEX API
    SECURITY_TYPES = {
        "обыкновенная акция": "common_share",
        "привилегированная акция": "preferred_share",
        "корпоративная облигация": "corporate_bond",
        "биржевая облигация": "exchange_bond",
    }

    # Обратный маппинг для отображения пользователю
    TYPE_DISPLAY_NAMES = {
        "common_share": "обыкновенная акция",
        "preferred_share": "привилегированная акция",
        "corporate_bond": "корпоративная облигация",
        "exchange_bond": "биржевая облигация",
    }

    def __init__(self, timeout: float = 30.0):
        """
        Инициализация парсера MOEX.

        Args:
            timeout: Таймаут запроса в секундах
        """
        self.timeout = timeout
        self.client: httpx.AsyncClient | None = None
        self.base_url = "https://iss.moex.com/iss"

    async def __aenter__(self):
        """Вход в контекстный менеджер."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекстного менеджера."""
        await self.close()

    async def start(self) -> None:
        """Инициализация HTTP клиента."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )

    async def close(self) -> None:
        """Закрытие HTTP клиента."""
        if self.client:
            await self.client.aclose()
            self.client = None

    async def get_securities_info(self, search_query: str) -> pd.DataFrame:
        """
        Получение информации о ценных бумагах по поисковому запросу.

        Args:
            search_query: Поисковый запрос (название банка или тикер)

        Returns:
            DataFrame с информацией о найденных ценных бумагах
        """
        if not self.client:
            await self.start()

        url = f"{self.base_url}/securities.json"
        params = {"q": search_query}

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            cols = data["securities"]["columns"]
            securities_data = data["securities"]["data"]

            df = pd.DataFrame(securities_data, columns=cols)
            return df
        except Exception as e:
            print(f"Ошибка при получении информации о ценных бумагах: {e}")
            return pd.DataFrame()

    async def get_candles(
        self,
        secid: str,
        board: str = "TQBR",
        date_from: str | None = None,
        date_till: str | None = None,
        interval: int = 24,
    ) -> pd.DataFrame:
        """
        Загрузка исторических данных (свечей) по тикеру.

        Args:
            secid: Тикер ценной бумаги (например, "SBER", "SBERP")
            board: Торговая площадка (по умолчанию "TQBR")
            date_from: Дата начала периода в формате "YYYY-MM-DD"
            date_till: Дата окончания периода в формате "YYYY-MM-DD"
            interval: Интервал свечей (1, 10, 60, 24 и т.д.)

        Returns:
            DataFrame с историческими данными о котировках
        """
        if not self.client:
            await self.start()

        # Устанавливаем значения по умолчанию для дат
        if date_from is None:
            date_from = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        if date_till is None:
            date_till = datetime.now().strftime("%Y-%m-%d")

        url = (
            f"{self.base_url}/engines/stock/"
            f"markets/shares/boards/{board}/securities/{secid}/candles.json"
        )

        params = {
            "from": date_from,
            "till": date_till,
            "interval": interval,
        }

        print("Запрос к MOEX API:")
        print(f"   URL: {url}")
        print(f"   Параметры: {params}")

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # Диагностика: проверяем структуру ответа
            print("Структура ответа API:")
            print(f"   Ключи верхнего уровня: {list(data.keys())}")

            if "candles" not in data:
                print("Ключ 'candles' не найден в ответе")
                print(f"   Доступные ключи: {list(data.keys())}")
                # Попробуем найти альтернативные ключи
                for key in data.keys():
                    if isinstance(data[key], dict) and "columns" in data[key]:
                        print(f"   Найден альтернативный ключ: {key}")
                        cols = data[key]["columns"]
                        candles_data = data[key]["data"]
                        df = pd.DataFrame(candles_data, columns=cols)
                        print(f"Получено {len(df)} записей через ключ '{key}'")
                        return df
                return pd.DataFrame()

            cols = data["candles"]["columns"]
            candles_data = data["candles"]["data"]

            print(f"   Колонки: {cols}")
            print(f"   Количество записей: {len(candles_data)}")

            if not candles_data:
                print("Данные свечей пусты")
                # Проверяем, есть ли информация об ошибке в ответе
                if "error" in data:
                    print(f"   Ошибка от API: {data['error']}")
                # Пробуем другие торговые площадки
                print("🔄 Пробуем другие торговые площадки...")
                alternative_boards = ["TQTF", "EQBR", "EQEU", "SMAL"]
                for alt_board in alternative_boards:
                    print(f"   Пробуем площадку: {alt_board}")
                    alt_url = url.replace(f"/{board}/", f"/{alt_board}/")
                    try:
                        alt_response = await self.client.get(alt_url, params=params)
                        alt_response.raise_for_status()
                        alt_data = alt_response.json()
                        if "candles" in alt_data and alt_data["candles"]["data"]:
                            print(f"   Найдены данные на площадке {alt_board}!")
                            cols = alt_data["candles"]["columns"]
                            candles_data = alt_data["candles"]["data"]
                            df = pd.DataFrame(candles_data, columns=cols)
                            return df
                    except Exception as alt_e:
                        print(f"   Ошибка на {alt_board}: {alt_e}")
                        continue

            df = pd.DataFrame(candles_data, columns=cols)

            if df.empty:
                print("DataFrame создан, но пуст")
            else:
                print(f"Успешно создан DataFrame с {len(df)} строками")
                print(f"   Колонки в DataFrame: {list(df.columns)}")

            return df
        except httpx.HTTPStatusError as e:
            print(f"HTTP ошибка {e.response.status_code}: {e.response.text[:200]}")
            return pd.DataFrame()
        except Exception as e:
            print(f"Ошибка при получении данных о котировках: {e}")

            traceback.print_exc()
            return pd.DataFrame()

    async def parse_securities(
        self,
        bank_choice: str,
        security_type: str | None = None,
        date_from: str | None = None,
        date_till: str | None = None,
        interval: int = 24,
    ) -> dict[str, Any]:
        """
        Полный цикл парсинга: получение информации о ценных бумагах и котировок.

        Args:
            bank_choice: Выбор банка ("1"-"5")
            security_type: Тип ценной бумаги (из SECURITY_TYPES)
            date_from: Дата начала периода в формате "YYYY-MM-DD"
            date_till: Дата окончания периода в формате "YYYY-MM-DD"
            interval: Интервал свечей

        Returns:
            Словарь с данными о ценных бумагах и котировках
        """
        if bank_choice not in self.BANK_NAMES:
            return {
                "error": f"Неверный выбор банка: {bank_choice}",
                "bank_info": None,
                "securities": pd.DataFrame(),
                "candles": pd.DataFrame(),
                "charts_generated": False,
            }

        bank_info = self.BANK_NAMES[bank_choice]
        search_query = bank_info["search"]

        print(f"Поиск ценных бумаг для: {bank_info['display']}")

        # Получаем информацию о ценных бумагах
        securities_df = await self.get_securities_info(search_query)

        if securities_df.empty:
            return {
                "error": "Не найдено ценных бумаг",
                "bank_info": bank_info,
                "securities": pd.DataFrame(),
                "candles": pd.DataFrame(),
                "charts_generated": False,
            }

        # Фильтруем по типу, если указан
        if security_type:
            if security_type in self.SECURITY_TYPES:
                type_value = self.SECURITY_TYPES[security_type]
                securities_df = securities_df[securities_df["type"] == type_value]

        result = {
            "bank_info": bank_info,
            "securities": securities_df,
            "candles": pd.DataFrame(),
            "charts_generated": False,
        }

        return result

    def _format_candles_dataframe(
        self,
        df: pd.DataFrame,
        secid: str,
        shortname: str,
    ) -> pd.DataFrame:
        """
        Форматирует датафрейм свечей к стандартному виду с нужными столбцами.

        Args:
            df: Исходный датафрейм со свечами
            secid: Тикер ценной бумаги
            shortname: Краткое название ценной бумаги

        Returns:
            Отформатированный датафрейм с столбцами: open, close, high, low, value, volume, begin, end, secid, shortname
        """
        if df.empty:
            return pd.DataFrame(
                columns=[
                    "open",
                    "close",
                    "high",
                    "low",
                    "value",
                    "volume",
                    "begin",
                    "end",
                    "secid",
                    "shortname",
                ]
            )

        # Создаем копию датафрейма
        formatted_df = df.copy()

        # Проверяем наличие необходимых столбцов и переименовываем при необходимости
        column_mapping = {
            "OPEN": "open",
            "CLOSE": "close",
            "HIGH": "high",
            "LOW": "low",
            "VALUE": "value",
            "VOLUME": "volume",
            "BEGIN": "begin",
            "END": "end",
        }

        # Переименовываем столбцы если они в верхнем регистре
        for old_col, new_col in column_mapping.items():
            if old_col in formatted_df.columns and new_col not in formatted_df.columns:
                formatted_df = formatted_df.rename(columns={old_col: new_col})

        # Выбираем только нужные столбцы (если они есть)
        required_columns = [
            "open",
            "close",
            "high",
            "low",
            "value",
            "volume",
            "begin",
            "end",
        ]
        available_columns = [
            col for col in required_columns if col in formatted_df.columns
        ]

        # Создаем новый датафрейм с нужными столбцами
        result_df = formatted_df[available_columns].copy()

        # Добавляем недостающие столбцы с нулевыми значениями
        for col in required_columns:
            if col not in result_df.columns:
                result_df[col] = 0.0 if col != "volume" else 0

        # Добавляем идентификаторы
        result_df["secid"] = secid
        result_df["shortname"] = shortname

        # Убеждаемся, что begin и end в правильном формате
        if "begin" in result_df.columns:
            result_df["begin"] = pd.to_datetime(result_df["begin"])
        if "end" in result_df.columns:
            result_df["end"] = pd.to_datetime(result_df["end"])

        # Упорядочиваем столбцы
        column_order = [
            "open",
            "close",
            "high",
            "low",
            "value",
            "volume",
            "begin",
            "end",
            "secid",
            "shortname",
        ]
        result_df = result_df[column_order]

        return result_df

    async def _plot_candles_from_dataframe(
        self,
        df: pd.DataFrame,
        secid: str,
        interval: int = 24,
    ) -> dict[str, Any]:
        """
        Строит графики из готового датафрейма.

        Args:
            df: Датафрейм со свечами
            secid: Тикер ценной бумаги
            interval: Интервал свечей для правильного форматирования оси X

        Returns:
            Словарь с информацией о построенных графиках
        """
        try:

            # Определяем формат оси X в зависимости от интервала
            if interval == 1:  # 1 минута
                date_format = mdates.DateFormatter("%Y-%m-%d %H:%M")
                locator = mdates.MinuteLocator(interval=60)  # каждые 60 минут
            elif interval == 10:  # 10 минут
                date_format = mdates.DateFormatter("%Y-%m-%d %H:%M")
                locator = mdates.HourLocator(interval=1)  # каждый час
            elif interval == 60:  # 1 час
                date_format = mdates.DateFormatter("%Y-%m-%d %H:%M")
                locator = mdates.HourLocator(interval=6)  # каждые 6 часов
            elif interval == 24:  # 1 день
                date_format = mdates.DateFormatter("%Y-%m-%d")
                locator = mdates.DayLocator(interval=max(1, len(df) // 30))  # адаптивно
            elif interval == 7:  # 1 неделя
                date_format = mdates.DateFormatter("%Y-%m-%d")
                locator = mdates.WeekLocator()
            elif interval in [31, 4, 12]:  # месяц, квартал, год
                date_format = mdates.DateFormatter("%Y-%m")
                locator = mdates.MonthLocator(interval=max(1, interval // 24))
            else:
                date_format = mdates.DateFormatter("%Y-%m-%d")
                locator = mdates.AutoDateLocator()

            # График 1: Цены закрытия
            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(df["begin"], df["close"], label=f"{secid} close", linewidth=1.5)
            ax.set_xlabel("Дата", fontsize=11)
            ax.set_ylabel("Цена, RUB", fontsize=11)
            ax.set_title(f"{secid} — цены закрытия", fontsize=12, fontweight="bold")
            ax.grid(True, alpha=0.3)
            ax.legend()

            # Применяем форматирование оси X
            ax.xaxis.set_major_formatter(date_format)
            ax.xaxis.set_major_locator(locator)
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
            plt.tight_layout()
            plt.show()

            # Вычисляем доходность
            df["ret_simple"] = df["close"].pct_change()
            df["ret_log"] = np.log(df["close"] / df["close"].shift(1))

            # График 2: Доходность
            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(df["begin"], df["ret_simple"], label="Daily return", linewidth=1.5)
            ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
            ax.set_xlabel("Дата", fontsize=11)
            ax.set_ylabel("Доходность", fontsize=11)
            ax.set_title("Доходность по цене закрытия", fontsize=12, fontweight="bold")
            ax.grid(True, alpha=0.3)
            ax.legend()

            # Применяем форматирование оси X
            ax.xaxis.set_major_formatter(date_format)
            ax.xaxis.set_major_locator(locator)
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
            plt.tight_layout()
            plt.show()

            return {"charts_generated": True}
        except Exception as e:
            print(f"Ошибка при построении графиков: {e}")
            traceback.print_exc()
            return {"charts_generated": False, "error": str(e)}

    async def get_and_plot_candles(
        self,
        secid: str,
        date_from: str | None = None,
        date_till: str | None = None,
        interval: int = 24,
        board: str = "TQBR",
        plot: bool = True,
    ) -> dict[str, Any]:
        """
        Получение данных о котировках и построение графиков.

        Args:
            secid: Тикер ценной бумаги
            date_from: Дата начала периода
            date_till: Дата окончания периода
            interval: Интервал свечей
            board: Торговая площадка
            plot: Строить ли графики

        Returns:
            Словарь с данными и информацией о графиках
        """
        # Получаем данные
        df = await self.get_candles(secid, board, date_from, date_till, interval)

        print("\nРезультат загрузки данных:")
        print(f"   Тикер: {secid}")
        print(f"   Площадка: {board}")
        print(f"   Период: {date_from} - {date_till}")
        print(f"   Размер DataFrame: {df.shape if not df.empty else 'пуст'}")

        if df.empty:
            print("\nDataFrame пуст. Проводим диагностику...")
            print(f"   Тикер: {secid}")
            print(f"   Площадка: {board}")
            print(f"   Период: {date_from} - {date_till}")

            # Проверяем информацию о тикере для определения правильной площадки
            print(f"\nПроверяем информацию о тикере {secid} в базе MOEX...")
            try:
                sec_info = await self.get_securities_info(secid)
                if not sec_info.empty:
                    print(f"   Найдено записей: {len(sec_info)}")
                    # Ищем точное совпадение по secid
                    matching = sec_info[sec_info["secid"] == secid]
                    if matching.empty:
                        # Пробуем найти похожие
                        matching = sec_info[
                            sec_info["shortname"].str.contains(
                                secid, case=False, na=False
                            )
                        ]

                    if not matching.empty:
                        print(f"   📋 Найденные записи для тикера {secid}:")
                        for idx, row in matching.head(5).iterrows():
                            secid_val = row.get("secid", "N/A")
                            # Используем primary_boardid как основной источник
                            board_val = row.get("primary_boardid", "N/A")
                            if board_val == "N/A" or pd.isna(board_val):
                                # Запасной вариант - board
                                board_val = row.get("board", "N/A")
                            type_val = row.get("type", "N/A")
                            name_val = row.get("shortname") or row.get("name", "N/A")
                            isin_val = row.get("isin", "N/A")
                            print(f"     - {name_val}")
                            print(
                                f"       Тикер: {secid_val}, Площадка (primary_boardid): {board_val}"
                            )
                            print(f"       Тип: {type_val}, ISIN: {isin_val}")

                            # Пробуем использовать правильную площадку
                            if (
                                board_val != "N/A"
                                and board_val != board
                                and board_val
                                and not pd.isna(board_val)
                            ):
                                print(
                                    f"   🔄 Пробуем площадку из данных MOEX: {board_val}"
                                )
                                df_retry = await self.get_candles(
                                    secid, str(board_val), date_from, date_till, interval
                                )
                                if not df_retry.empty:
                                    print(
                                        f"   Данные найдены на площадке {board_val}!"
                                    )
                                    df = df_retry
                                    break
                    else:
                        print(f"   Точное совпадение для тикера {secid} не найдено")
                        print(
                            f"   Всего найдено записей с похожим названием: {len(sec_info)}"
                        )
                else:
                    print(f"   Тикер {secid} не найден в базе MOEX")
                    print(
                        "   Проверьте правильность тикера. Возможно, нужно использовать другой тикер."
                    )
            except Exception as e:
                print(f"   Ошибка при проверке тикера: {e}")
                traceback.print_exc()

            if df.empty:
                print(f"\nНе удалось получить данные для тикера {secid}")
                print("   Возможные причины:")
                print(f"   1. Тикер не торгуется на площадке {board}")
                print("   2. Нет данных за указанный период")
                print(
                    "   3. Для этого типа инструмента (фиксинг/индекс) нет исторических данных"
                )
                print(
                    "   4. Попробуйте выбрать другую ценную бумагу (акцию вместо фиксинга)"
                )

                return {
                    "secid": secid,
                    "candles": pd.DataFrame(),
                    "charts_generated": False,
                    "error": f"Нет данных для построения графиков. Тикер: {secid}, Площадка: {board}, Период: {date_from} - {date_till}",
                }

        print(f"Данные успешно получены: {len(df)} записей")
        if "begin" in df.columns:
            print(f"   Период данных: {df['begin'].min()} - {df['begin'].max()}")

        # Конвертируем дату
        df["begin"] = pd.to_datetime(df["begin"])

        charts_info = {
            "secid": secid,
            "candles": df,
            "charts_generated": False,
        }

        # Форматируем датафрейм к стандартному виду
        df = self._format_candles_dataframe(df, secid, secid)
        charts_info["candles"] = df

        if plot and not df.empty:
            try:
                charts_plot_result = await self._plot_candles_from_dataframe(
                    df, secid, interval
                )
                charts_info["charts_generated"] = charts_plot_result.get(
                    "charts_generated", False
                )
                if "error" in charts_plot_result:
                    charts_info["error"] = charts_plot_result["error"]
            except Exception as e:
                print(f"Ошибка при построении графиков: {e}")
                charts_info["error"] = str(e)

        return charts_info

    async def interactive_parse(self) -> dict[str, Any]:
        """
        Интерактивный режим парсинга с вводом данных от пользователя.

        Returns:
            Словарь с результатами парсинга
        """
        print("=" * 60)
        print("Парсер ценных бумаг Московской биржи (MOEX)")
        print("=" * 60)

        # Выбор банка
        print("\nВыберите организацию, по которой хотели бы получить котировки:")
        for key, value in self.BANK_NAMES.items():
            print(f"{key}. {value['display']}")

        bank_choice = input("\nВведите цифру: ").strip()

        if bank_choice not in self.BANK_NAMES:
            return {
                "error": f"Неверный выбор банка: {bank_choice}",
                "bank_info": None,
                "securities": pd.DataFrame(),
                "candles": pd.DataFrame(),
                "charts_generated": False,
            }

        # Получаем информацию о ценных бумагах
        bank_info = self.BANK_NAMES[bank_choice]
        securities_df = await self.get_securities_info(bank_info["search"])

        if securities_df.empty:
            print(f"\nНе найдено ценных бумаг для: {bank_info['display']}")
            return {
                "error": "Не найдено ценных бумаг",
                "bank_info": bank_info,
                "securities": pd.DataFrame(),
                "candles": pd.DataFrame(),
                "charts_generated": False,
            }

        # Определяем доступные типы ценных бумаг
        filtered_securities = None
        selected_type = None

        if "type" not in securities_df.columns:
            print("Колонка 'type' не найдена в данных. Показываем все ценные бумаги.")
            filtered_securities = securities_df
        else:
            available_types = securities_df["type"].unique()

            print(f"\nНайдено {len(securities_df)} ценных бумаг")
            print("\nДоступные типы ценных бумаг:")

            type_options = {}
            idx = 1
            for sec_type in available_types:
                # Используем display name если есть, иначе сам тип
                display_name = self.TYPE_DISPLAY_NAMES.get(sec_type, sec_type)
                type_options[str(idx)] = sec_type
                securities_of_type = securities_df[securities_df["type"] == sec_type]
                print(f"{idx}. {display_name} ({len(securities_of_type)} шт.)")
                idx += 1

            if not type_options:
                print("Не найдено известных типов ценных бумаг. Показываем все.")
                filtered_securities = securities_df
            else:
                type_choice = input("\nВведите номер типа ценной бумаги: ").strip()

                if type_choice not in type_options:
                    return {
                        "error": f"Неверный выбор типа: {type_choice}",
                        "bank_info": bank_info,
                        "securities": securities_df,
                        "candles": pd.DataFrame(),
                        "charts_generated": False,
                    }

                selected_type = type_options[type_choice]
                filtered_securities = securities_df[
                    securities_df["type"] == selected_type
                ]

        if filtered_securities is None or filtered_securities.empty:
            error_msg = "Не найдено ценных бумаг" + (
                f" типа '{selected_type}'" if selected_type else ""
            )
            return {
                "error": error_msg,
                "bank_info": bank_info,
                "securities": securities_df,
                "candles": pd.DataFrame(),
                "charts_generated": False,
            }

        # Выбор конкретной ценной бумаги или всех
        if (
            "type" in filtered_securities.columns
            and len(filtered_securities["type"].unique()) == 1
        ):
            display_name = self.TYPE_DISPLAY_NAMES.get(
                filtered_securities["type"].iloc[0], filtered_securities["type"].iloc[0]
            )
            print(f"\nДоступные ценные бумаги типа '{display_name}':")
        else:
            print("\nДоступные ценные бумаги:")

        shortnames = (
            filtered_securities["shortname"].tolist()
            if "shortname" in filtered_securities.columns
            else []
        )

        if not shortnames:
            # Если нет колонки shortname, используем другие варианты
            if "name" in filtered_securities.columns:
                shortnames = filtered_securities["name"].tolist()
            elif "secid" in filtered_securities.columns:
                shortnames = filtered_securities["secid"].tolist()
            else:
                shortnames = [str(i) for i in range(len(filtered_securities))]

        for i, shortname in enumerate(shortnames, 1):
            row = filtered_securities.iloc[i - 1]
            secid_val = (
                row.get("secid")
                if "secid" in row.index
                else (row.get("SECID") if "SECID" in row.index else "")
            )
            # Показываем также primary_boardid для информации
            board_val = (
                row.get("primary_boardid") if "primary_boardid" in row.index else None
            )
            if not board_val or pd.isna(board_val):
                board_val = row.get("board") if "board" in row.index else None

            if secid_val:
                board_info = (
                    f", площадка: {board_val}"
                    if board_val and not pd.isna(board_val)
                    else ""
                )
                print(f"{i}. {shortname} (тикер: {secid_val}{board_info})")
            else:
                print(f"{i}. {shortname}")

        print("0. Все ценные бумаги")

        security_choice = input("\nВведите номер ценной бумаги (0 для всех): ").strip()

        # Ввод периода дат
        print("\n📅 Введите период для получения котировок:")
        date_from = input(
            "Дата начала (YYYY-MM-DD) или Enter для последнего года: "
        ).strip()
        if not date_from:
            date_from = None

        date_till = input("Дата окончания (YYYY-MM-DD) или Enter для сегодня: ").strip()
        if not date_till:
            date_till = None

        # Ввод интервала
        print("\nВыберите интервал свечей:")
        print("1.  1 минута")
        print("2.  10 минут")
        print("3.  1 час")
        print("4.  1 день (по умолчанию)")
        print("5.  1 неделя")
        print("6.  1 месяц")
        print("7.  1 квартал")
        print("8.  1 год")

        interval_choice = input(
            "\nВведите номер интервала (1-8, по умолчанию 4): "
        ).strip()
        interval_map = {
            "1": 1,  # 1 минута
            "2": 10,  # 10 минут
            "3": 60,  # 1 час
            "4": 24,  # 1 день
            "5": 7,  # 1 неделя
            "6": 31,  # 1 месяц
            "7": 4,  # 1 квартал
            "8": 12,  # 1 год
        }
        interval = interval_map.get(interval_choice, 24)

        # Определяем название интервала для вывода
        interval_names = {
            1: "1 минута",
            10: "10 минут",
            60: "1 час",
            24: "1 день",
            7: "1 неделя",
            31: "1 месяц",
            4: "1 квартал",
            12: "1 год",
        }
        interval_name = interval_names.get(interval, f"{interval}")
        print(f"Выбран интервал: {interval_name}")

        # Определяем какие ценные бумаги обрабатывать
        selected_securities = []

        if security_choice == "0":
            # Обрабатываем все ценные бумаги
            print(f"\nОбработка всех {len(filtered_securities)} ценных бумаг...")
            selected_securities = filtered_securities.to_dict("records")
        else:
            try:
                security_idx = int(security_choice) - 1
                if security_idx < 0 or security_idx >= len(shortnames):
                    return {
                        "error": f"Неверный выбор: {security_choice}",
                        "bank_info": bank_info,
                        "securities": filtered_securities,
                        "candles": pd.DataFrame(),
                        "charts_generated": False,
                    }
                selected_security_row = filtered_securities.iloc[security_idx]
                selected_securities = [selected_security_row.to_dict()]
            except (ValueError, IndexError):
                return {
                    "error": f"Неверный формат номера или индекс вне диапазона: {security_choice}",
                    "bank_info": bank_info,
                    "securities": filtered_securities,
                    "candles": pd.DataFrame(),
                    "charts_generated": False,
                }

        # Собираем данные по всем выбранным ценным бумагам
        all_candles_dfs = []
        processed_securities = []

        for idx, security_row in enumerate(selected_securities):
            # Преобразуем dict обратно в Series для удобства работы
            if isinstance(security_row, dict):
                security_row = pd.Series(security_row)

            selected_shortname = (
                security_row.get("shortname")
                if "shortname" in security_row.index
                else security_row.get("name", "")
            )

            # Получаем secid из строки DataFrame
            secid = None
            if "secid" in security_row.index:
                secid = security_row["secid"]
            elif "SECID" in security_row.index:
                secid = security_row["SECID"]

            # Если secid не найден или пустой, используем shortname
            if not secid or (isinstance(secid, float) and pd.isna(secid)):
                secid = selected_shortname

            # Получаем торговую площадку из данных о ценной бумаге
            # Используем primary_boardid согласно структуре данных MOEX
            board_from_data = None
            if "primary_boardid" in security_row.index:
                board_val = security_row.get("primary_boardid")
                if board_val is not None and not pd.isna(board_val):
                    board_from_data = str(board_val)
            # Если primary_boardid нет, пробуем board как запасной вариант
            if not board_from_data and "board" in security_row.index:
                board_val = security_row.get("board")
                if board_val is not None and not pd.isna(board_val):
                    board_from_data = str(board_val)
            # Если ничего не нашли, используем TQBR по умолчанию
            if not board_from_data:
                board_from_data = "TQBR"

            print(
                f"\n📈 [{idx + 1}/{len(selected_securities)}] Загрузка данных для {selected_shortname} (тикер: {secid}, площадка: {board_from_data})..."
            )

            # Получаем котировки (без построения графиков для каждой отдельно)
            df = await self.get_candles(
                secid=secid,
                board=board_from_data,
                date_from=date_from,
                date_till=date_till,
                interval=interval,
            )

            if not df.empty:
                # Приводим датафрейм к нужному формату
                df = self._format_candles_dataframe(df, secid, selected_shortname)
                all_candles_dfs.append(df)
                processed_securities.append(
                    {
                        "secid": secid,
                        "shortname": selected_shortname,
                        "rows_count": len(df),
                    }
                )
                print(f"   Получено {len(df)} записей")
            else:
                print("   Данные не найдены")
                processed_securities.append(
                    {
                        "secid": secid,
                        "shortname": selected_shortname,
                        "rows_count": 0,
                        "error": "Данные не найдены",
                    }
                )

        # Объединяем все датафреймы
        if all_candles_dfs:
            combined_df = pd.concat(all_candles_dfs, ignore_index=True)

            # Сортируем по дате начала
            if "begin" in combined_df.columns:
                combined_df["begin"] = pd.to_datetime(combined_df["begin"])
                combined_df = combined_df.sort_values("begin").reset_index(drop=True)

            print(
                f"\nИтого получено {len(combined_df)} записей по {len(all_candles_dfs)} ценным бумагам"
            )

            # Строим графики только если выбрана одна ценная бумага
            charts_generated = False
            if len(selected_securities) == 1 and not combined_df.empty:
                print("\nПостроение графиков...")
                charts_info = await self._plot_candles_from_dataframe(
                    combined_df, processed_securities[0]["secid"], interval=interval
                )
                charts_generated = charts_info.get("charts_generated", False)
        else:
            combined_df = pd.DataFrame(
                columns=[
                    "open",
                    "close",
                    "high",
                    "low",
                    "value",
                    "volume",
                    "begin",
                    "end",
                    "secid",
                    "shortname",
                ]
            )
            charts_generated = False

        return {
            "bank_info": bank_info,
            "securities_info": processed_securities,
            "candles": combined_df,
            "charts_generated": charts_generated,
            "interval": interval,
            "date_from": date_from,
            "date_till": date_till,
        }
