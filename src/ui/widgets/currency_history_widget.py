import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
import qasync
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot


class CurrencyHistoryWidget(QWidget):
    """Виджет для отображения истории валют."""

    ARCHIVE_URL = "https://www.cbr-xml-daily.ru/archive/{year}/{month:02d}/{day:02d}/daily_json.js"
    POPULAR = ["USD", "EUR", "CNY", "GBP", "JPY"]
    MIN_DATE = datetime(1995, 7, 1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("История валют")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # --- Controls ---
        controls = QHBoxLayout()
        controls.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.currency_box = QComboBox()
        self.currency_box.setMinimumWidth(300)
        controls.addWidget(QLabel("Валюта:"))
        controls.addWidget(self.currency_box)

        last_day = QDate.currentDate().addDays(-1)

        self.start_date = QDateEdit(calendarPopup=True)
        self.start_date.setDate(last_day.addDays(-7))
        controls.addWidget(QLabel("Начало:"))
        controls.addWidget(self.start_date)

        self.end_date = QDateEdit(calendarPopup=True)
        self.end_date.setDate(QDate.currentDate())
        controls.addWidget(QLabel("Конец:"))
        controls.addWidget(self.end_date)

        self.update_btn = QPushButton("Обновить")
        self.update_btn.clicked.connect(self.update_chart)  # asyncSlot
        controls.addWidget(self.update_btn)

        layout.addLayout(controls)

        # --- Charts ---
        self.fig = Figure(figsize=(10, 5))
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)

        self.ax_value = self.fig.add_subplot(211)
        self.ax_delta = self.fig.add_subplot(212)

        asyncio.create_task(self._load_valutes())

    async def _fetch_json(self, session: httpx.AsyncClient, date: datetime) -> dict | None:
        """Загружаем JSON ЦБ на указанную дату (если нет, идём назад)."""
        while date >= self.MIN_DATE:
            url = self.ARCHIVE_URL.format(year=date.year, month=date.month, day=date.day)
            try:
                resp = await session.get(url, timeout=10.0)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    date -= timedelta(days=1)
                    continue
                return None
            except Exception:
                return None
        return None

    async def _load_valutes(self):
        """Загружает список валют."""
        async with httpx.AsyncClient(timeout=15.0) as session:
            data = await self._fetch_json(session, datetime.now())
            valutes = {c: v["Name"] for c, v in data.get("Valute", {}).items()} if data else {}

        if not valutes:
            QMessageBox.critical(self, "Ошибка", "Не удалось загрузить список валют")
            return

        # Сначала популярные в нужном порядке
        for code in self.POPULAR:
            if code in valutes:
                self.currency_box.addItem(f"{code} - {valutes[code]}", code)

        # Потом остальные (по алфавиту)
        other_codes = sorted(c for c in valutes if c not in self.POPULAR)
        for code in other_codes:
            self.currency_box.addItem(f"{code} - {valutes[code]}", code)

    async def _fetch_rate(
        self, session: httpx.AsyncClient, code: str, date: datetime
    ) -> dict[str, Any] | None:
        """Загружает курс валюты на указанную дату."""
        data = await self._fetch_json(session, date)
        if not data:
            return None
        v = data.get("Valute", {}).get(code)
        if not v:
            return None
        return {
            "date": datetime.fromisoformat(data["Date"]),
            "value": v["Value"],
            "previous": v["Previous"],
        }

    async def _fetch_rates(
        self, code: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """Загружает курсы валют за период."""
        results = []
        async with httpx.AsyncClient(timeout=15.0) as session:
            for offset in range((end - start).days + 1):
                date = start + timedelta(days=offset)
                rate = await self._fetch_rate(session, code, date)
                if rate:
                    results.append(rate)
        return results

    @asyncSlot()
    async def update_chart(self):
        """Обновляет график."""
        code = self.currency_box.currentData()
        if not code:
            QMessageBox.warning(self, "Ошибка", "Валюта не выбрана")
            return

        start = datetime.combine(self.start_date.date().toPyDate(), datetime.min.time())
        end = datetime.combine(self.end_date.date().toPyDate(), datetime.min.time())

        if start.date() > datetime.now().date() or end.date() > datetime.now().date():
            QMessageBox.warning(self, "Ошибка", "Нельзя выбирать дату позже сегодняшней")
            return

        self.update_btn.setEnabled(False)
        self.ax_value.clear()
        self.ax_delta.clear()

        rates = await self._fetch_rates(code, start, end)
        if not rates:
            self.ax_value.text(0.5, 0.5, "Нет данных", ha="center")
            self.canvas.draw()
            self.update_btn.setEnabled(True)
            return

        dates = [r["date"] for r in rates]
        values = [r["value"] for r in rates]
        deltas = [r["value"] - r["previous"] for r in rates]

        self._plot_value_chart(code, dates, values)
        self._plot_delta_chart(code, dates, deltas)

        self.fig.autofmt_xdate()
        self.canvas.draw()
        self.update_btn.setEnabled(True)

    def _plot_value_chart(self, code: str, dates, values):
        """Строит график значений."""
        self.ax_value.plot(dates, values, marker="o", linestyle="-")
        self.ax_value.set_title(f"{code} - курс")
        self.ax_value.grid(True)
        self.ax_value.xaxis.set_major_locator(MaxNLocator(nbins=10, prune="both"))
        self.ax_value.yaxis.set_major_locator(MaxNLocator(nbins=10))
        self.ax_value.margins(x=0.1, y=0.1)

    def _plot_delta_chart(self, code: str, dates, deltas):
        """Строит график изменений."""
        colors = ["#008000" if d > 0 else "#8B0000" if d < 0 else "#696969" for d in deltas]
        self.ax_delta.bar(dates, deltas, color=colors)
        self.ax_delta.set_title(f"{code} - изменение курса")
        self.ax_delta.grid(True)
        self.ax_delta.xaxis.set_major_locator(MaxNLocator(nbins=10, prune="both"))
        self.ax_delta.margins(x=0.1, y=0.1)
