import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
import qasync
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
import matplotlib.dates as mdates
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
        self._theme_colors = {
            "background": "#FFFFFF",
            "text": "#000000",
            "grid": "#E0E0E0",
            "axes": "#000000",
        }

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
        # Увеличиваем высоту фигуры, чтобы было больше места для графиков
        self.fig = Figure(figsize=(10, 7))
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)

        # Создаем subplot с увеличенными отступами между графиками
        self.ax_value = self.fig.add_subplot(211)
        self.ax_delta = self.fig.add_subplot(212)

        # Увеличиваем отступы между графиками, чтобы даты влезли
        # hspace=0.6 дает примерно 2 см дополнительного пространства между графиками
        self.fig.subplots_adjust(hspace=0.6, bottom=0.15, top=0.95)

        # Применяем начальные цвета темы
        self._apply_theme_colors()

        asyncio.create_task(self._load_valutes())

    def update_theme_colors(self, theme_colors: dict):
        """
        Обновляет цвета графиков в соответствии с темой.

        Args:
            theme_colors: Словарь с цветами темы (background, text, grid, axes)
        """
        self._theme_colors = theme_colors
        self._apply_theme_colors()
        # Обновляем графики, если они уже отображены
        # Проверяем, есть ли данные на графиках
        has_value_data = hasattr(self, 'ax_value') and len(self.ax_value.lines) > 0
        has_delta_data = hasattr(self, 'ax_delta') and len(self.ax_delta.patches) > 0

        if has_value_data or has_delta_data:
            # Перерисовываем графики с новыми цветами
            # Обновляем цвета сетки для обоих графиков
            if has_value_data:
                self.ax_value.grid(True, color=self._theme_colors["grid"], alpha=0.3)
            if has_delta_data:
                self.ax_delta.grid(True, color=self._theme_colors["grid"], alpha=0.3)
            # Перерисовываем canvas
            self.canvas.draw()

    def _apply_theme_colors(self):
        """Применяет цвета темы к графикам."""
        self.fig.patch.set_facecolor(self._theme_colors["background"])
        self.ax_value.set_facecolor(self._theme_colors["background"])
        self.ax_delta.set_facecolor(self._theme_colors["background"])

        # Цвета текста и осей
        self.ax_value.tick_params(colors=self._theme_colors["text"])
        self.ax_delta.tick_params(colors=self._theme_colors["text"])
        self.ax_value.xaxis.label.set_color(self._theme_colors["text"])
        self.ax_value.yaxis.label.set_color(self._theme_colors["text"])
        self.ax_delta.xaxis.label.set_color(self._theme_colors["text"])
        self.ax_delta.yaxis.label.set_color(self._theme_colors["text"])
        self.ax_value.title.set_color(self._theme_colors["text"])
        self.ax_delta.title.set_color(self._theme_colors["text"])

        # Цвета осей
        for ax in [self.ax_value, self.ax_delta]:
            ax.spines['bottom'].set_color(self._theme_colors["axes"])
            ax.spines['top'].set_color(self._theme_colors["axes"])
            ax.spines['right'].set_color(self._theme_colors["axes"])
            ax.spines['left'].set_color(self._theme_colors["axes"])

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
            # Применяем цвета темы даже когда нет данных
            self._apply_theme_colors()
            self.ax_value.text(0.5, 0.5, "Нет данных", ha="center", color=self._theme_colors["text"])
            self.canvas.draw()
            self.update_btn.setEnabled(True)
            return

        dates = [r["date"] for r in rates]
        values = [r["value"] for r in rates]
        deltas = [r["value"] - r["previous"] for r in rates]

        self._plot_value_chart(code, dates, values)
        self._plot_delta_chart(code, dates, deltas)

        # Автоматическое форматирование дат на обеих осях X
        # Убеждаемся, что форматирование дат применено к обеим осям
        if dates and len(dates) > 0:
            for ax in [self.ax_value, self.ax_delta]:
                try:
                    # Проверяем, что форматирование дат действительно применено
                    formatter = ax.xaxis.get_major_formatter()
                    if not isinstance(formatter, mdates.DateFormatter):
                        date_format = mdates.DateFormatter("%d.%m.%Y")
                        ax.xaxis.set_major_formatter(date_format)
                    # Явно включаем отображение меток
                    ax.tick_params(axis='x', labelbottom=True)
                    # Убеждаемся, что все метки видны
                    for label in ax.get_xticklabels():
                        label.set_visible(True)
                except Exception as e:
                    print(f"Ошибка при применении форматирования дат: {e}")
        # Автоматическое форматирование дат (применяется к обеим осям)
        self.fig.autofmt_xdate()
        # Явно включаем метки на обеих осях после autofmt_xdate
        # (autofmt_xdate может скрыть метки на верхнем графике)
        self.ax_value.tick_params(axis='x', labelbottom=True)
        self.ax_delta.tick_params(axis='x', labelbottom=True)
        # Убеждаемся, что все метки видны и повернуты
        for label in self.ax_value.get_xticklabels():
            label.set_visible(True)
            label.set_rotation(45)
        for label in self.ax_delta.get_xticklabels():
            label.set_visible(True)
            label.set_rotation(45)
        # Обновляем отступы после форматирования
        # hspace=0.6 дает примерно 2 см дополнительного пространства между графиками
        self.fig.subplots_adjust(hspace=0.6, bottom=0.15, top=0.95)
        self.canvas.draw()
        self.update_btn.setEnabled(True)

    def _plot_value_chart(self, code: str, dates, values):
        """Строит график значений."""
        # Применяем цвета темы перед построением
        self._apply_theme_colors()
        self.ax_value.plot(dates, values, marker="o", linestyle="-")
        self.ax_value.set_title(f"{code} - курс")
        self.ax_value.grid(True, color=self._theme_colors["grid"], alpha=0.3)

        # Форматирование дат на оси X
        if dates and len(dates) > 0:
            try:
                days_span = (max(dates) - min(dates)).days
                num_points = len(dates)
                # Единый формат дат: день.месяц.год
                date_format = mdates.DateFormatter("%d.%m.%Y")
                # Адаптивный интервал в зависимости от периода (более частые даты)
                # Цель: показать примерно 8-12 дат на графике
                if days_span <= 7:
                    # Для недели - каждый день
                    locator = mdates.DayLocator(interval=1)
                elif days_span <= 31:
                    # Для месяца - каждые 2-3 дня
                    interval = max(1, days_span // 12)
                    locator = mdates.DayLocator(interval=interval)
                elif days_span <= 90:
                    # Для квартала - каждые 5-7 дней
                    interval = max(1, days_span // 12)
                    locator = mdates.DayLocator(interval=interval)
                elif days_span <= 365:
                    # Для года - каждые 2-3 недели
                    interval = max(1, days_span // 15)
                    locator = mdates.DayLocator(interval=interval)
                else:
                    # Для больше года - каждый месяц
                    locator = mdates.MonthLocator(interval=1)

                self.ax_value.xaxis.set_major_formatter(date_format)
                self.ax_value.xaxis.set_major_locator(locator)
            except Exception as e:
                # Если ошибка форматирования, используем стандартный формат с большим количеством бинов
                print(f"Ошибка форматирования дат на графике курса: {e}")
                try:
                    # Пробуем применить хотя бы базовое форматирование дат
                    date_format = mdates.DateFormatter("%d.%m.%Y")
                    self.ax_value.xaxis.set_major_formatter(date_format)
                    self.ax_value.xaxis.set_major_locator(MaxNLocator(nbins=15, prune="both"))
                except:
                    self.ax_value.xaxis.set_major_locator(MaxNLocator(nbins=15, prune="both"))
        else:
            # Если нет дат, используем стандартный формат
            self.ax_value.xaxis.set_major_locator(MaxNLocator(nbins=15, prune="both"))

        self.ax_value.yaxis.set_major_locator(MaxNLocator(nbins=10))
        self.ax_value.margins(x=0.05, y=0.1)
        # Явно включаем отображение дат на верхнем графике
        self.ax_value.tick_params(axis='x', labelbottom=True, labelsize=8)
        # Убеждаемся, что метки видны
        for label in self.ax_value.get_xticklabels():
            label.set_visible(True)
            label.set_rotation(45)

    def _plot_delta_chart(self, code: str, dates, deltas):
        """Строит график изменений."""
        # Применяем цвета темы перед построением
        self._apply_theme_colors()
        colors = ["#008000" if d > 0 else "#8B0000" if d < 0 else "#696969" for d in deltas]
        self.ax_delta.bar(dates, deltas, color=colors)
        self.ax_delta.set_title(f"{code} - изменение курса")
        self.ax_delta.grid(True, color=self._theme_colors["grid"], alpha=0.3)

        # Форматирование дат на оси X
        if dates:
            try:
                days_span = (max(dates) - min(dates)).days
                num_points = len(dates)
                # Единый формат дат: день.месяц.год
                date_format = mdates.DateFormatter("%d.%m.%Y")
                # Адаптивный интервал в зависимости от периода (более частые даты)
                # Цель: показать примерно 8-12 дат на графике
                if days_span <= 7:
                    # Для недели - каждый день
                    locator = mdates.DayLocator(interval=1)
                elif days_span <= 31:
                    # Для месяца - каждые 2-3 дня
                    interval = max(1, days_span // 12)
                    locator = mdates.DayLocator(interval=interval)
                elif days_span <= 90:
                    # Для квартала - каждые 5-7 дней
                    interval = max(1, days_span // 12)
                    locator = mdates.DayLocator(interval=interval)
                elif days_span <= 365:
                    # Для года - каждые 2-3 недели
                    interval = max(1, days_span // 15)
                    locator = mdates.DayLocator(interval=interval)
                else:
                    # Для больше года - каждый месяц
                    locator = mdates.MonthLocator(interval=1)

                self.ax_delta.xaxis.set_major_formatter(date_format)
                self.ax_delta.xaxis.set_major_locator(locator)
            except Exception:
                # Если ошибка форматирования, используем стандартный формат с большим количеством бинов
                self.ax_delta.xaxis.set_major_locator(MaxNLocator(nbins=15, prune="both"))

        self.ax_delta.margins(x=0.05, y=0.1)
        # У нижнего графика показываем даты на оси X
        self.ax_delta.tick_params(axis='x', labelbottom=True, rotation=45)
