import asyncio
from datetime import date, datetime
from typing import Any, Optional

import httpx
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.services.currency_rates_service import CurrencyRatesService


class NumericItem(QTableWidgetItem):
    """QTableWidgetItem, который сортируется как число."""

    def __init__(self, text: str, value: float):
        super().__init__(text)
        self._numeric_value = value

    def __lt__(self, other):
        if isinstance(other, NumericItem):
            return self._numeric_value < other._numeric_value
        return super().__lt__(other)


class RatesWidget(QWidget):
    """Виджет для отображения курсов валют."""

    URL = "https://www.cbr-xml-daily.ru/daily_json.js"
    POPULAR = ["USD", "EUR", "CNY", "GBP", "JPY"]

    def __init__(
        self, currency_rates_service: Optional[CurrencyRatesService] = None, parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Курсы ЦБ РФ")
        self.resize(700, 600)
        self._currency_rates_service = currency_rates_service

        self.label = QLabel("Загрузка…")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Код", "Номинал", "Валюта", "Курс", "Динамика"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)

        # Настройка размеров колонок
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Код
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Номинал
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Валюта
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Курс
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  # Динамика
        header.sectionClicked.connect(self.enable_sorting_on_click)

        self.refresh_btn = QPushButton("Обновить сейчас")
        self.refresh_btn.clicked.connect(
            lambda: asyncio.create_task(self._load_and_show(force_fetch=True))
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.refresh_btn)
        layout.addWidget(self.table)

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: asyncio.create_task(self._load_and_show()))
        self.timer.start(86_400_000)  # 24 часа

        self.client = httpx.AsyncClient(timeout=15.0)
        # Загружаем данные при инициализации
        asyncio.create_task(self._load_and_show())

    def enable_sorting_on_click(self):
        """Включает сортировку при клике на заголовок."""
        if not self.table.isSortingEnabled():
            self.table.setSortingEnabled(True)
        self.table.clearSelection()

    async def close_client(self):
        """Закрывает HTTP клиент."""
        await self.client.aclose()

    async def _fetch_rates(self) -> dict[str, Any]:
        """Загружает курсы валют."""
        resp = await self.client.get(self.URL)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _parse_data(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Парсит данные из JSON."""
        date_parsed = datetime.fromisoformat(data["Date"])
        items = [
            {
                "code": code,
                "name": info["Name"],
                "nominal": info["Nominal"],
                "value": info["Value"],
                "previous": info["Previous"],
                "date": date_parsed.strftime("%d.%m.%Y"),
            }
            for code, info in data.get("Valute", {}).items()
        ]
        return items

    @staticmethod
    def format_delta(value, previous):
        """Форматирует изменение курса."""
        delta = value - previous
        if delta > 0:
            return f"{delta:+.4f} ↑", QColor(60, 179, 113)
        elif delta < 0:
            return f"{delta:+.4f} ↓", QColor(220, 20, 60)
        else:
            return f"{delta:+.4f} —", QColor(105, 105, 105)

    async def _load_and_show(self, force_fetch: bool = False):
        """
        Загружает и отображает данные.

        Args:
            force_fetch: Если True, всегда парсит данные из API, иначе проверяет БД
        """
        data = None
        rate_date = None

        # Если есть сервис БД и не принудительная загрузка, проверяем БД
        if self._currency_rates_service and not force_fetch:
            try:
                # Проверяем, есть ли курсы на сегодня
                has_today = await self._currency_rates_service.has_rates_for_today()
                if has_today:
                    # Загружаем из БД
                    today = date.today()
                    data = await self._currency_rates_service.get_rates_by_date(today)
                    if data:
                        rate_date = datetime.combine(today, datetime.min.time())
            except Exception as e:
                print(f"Ошибка при загрузке из БД: {e}")

        # Если данных нет в БД или принудительная загрузка, парсим из API
        if not data or force_fetch:
            try:
                raw = await self._fetch_rates()
                parsed_data = self._parse_data(raw)

                # Получаем дату из ответа API
                rate_date_str = raw.get("Date", "")
                if rate_date_str:
                    try:
                        # Пытаемся распарсить дату с timezone
                        rate_date = datetime.fromisoformat(
                            rate_date_str.replace("Z", "+00:00")
                        )
                        # Конвертируем в локальное время без timezone
                        if rate_date.tzinfo:
                            rate_date = rate_date.replace(tzinfo=None)
                    except (ValueError, AttributeError):
                        # Если не удалось распарсить, используем текущую дату
                        rate_date = datetime.now().replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )

                data = parsed_data

                # Сохраняем в БД, если есть сервис
                if self._currency_rates_service and data and rate_date:
                    try:
                        # Подготавливаем данные для сохранения
                        rates_to_save = [
                            {
                                "code": item["code"],
                                "name": item["name"],
                                "nominal": item["nominal"],
                                "value": item["value"],
                                "previous": item["previous"],
                            }
                            for item in data
                        ]
                        await self._currency_rates_service.save_rates(
                            rates_to_save, rate_date
                        )
                    except Exception as e:
                        print(f"Ошибка при сохранении в БД: {e}")

            except Exception as exc:
                self.label.setText(f"Ошибка загрузки: {exc}")
                return

        if not data:
            self.label.setText("Нет данных")
            return

        # Определяем дату для отображения
        display_date = (
            rate_date.strftime("%d.%m.%Y")
            if rate_date
            else datetime.now().strftime("%d.%m.%Y")
        )
        self.label.setText(f"Курсы ЦБ РФ на {display_date}")
        self.table.setSortingEnabled(False)

        full_data = sorted(
            data,
            key=lambda x: (
                0 if x["code"] in self.POPULAR else 1,
                self.POPULAR.index(x["code"]) if x["code"] in self.POPULAR else 0,
            ),
        )

        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(full_data))

        for row, item in enumerate(full_data):
            delta_text, color = self.format_delta(item["value"], item["previous"])
            cells = [
                QTableWidgetItem(item["code"]),
                NumericItem(str(item["nominal"]), item["nominal"]),
                QTableWidgetItem(item["name"]),
                NumericItem(f"{item['value']:.4f}", item["value"]),
                NumericItem(delta_text, item["value"] - item["previous"]),
            ]
            for col, cell in enumerate(cells):
                if col == 4:
                    cell.setForeground(color)
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, col, cell)
        self.table.setUpdatesEnabled(True)

    def closeEvent(self, event):
        """Обработчик закрытия виджета."""
        asyncio.create_task(self.close_client())
        super().closeEvent(event)
