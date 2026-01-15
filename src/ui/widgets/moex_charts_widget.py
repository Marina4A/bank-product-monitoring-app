"""Виджет для отображения графиков ценных бумаг MOEX."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
except ImportError:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from matplotlib import dates as mdates
from matplotlib.figure import Figure

from core.parsers.moex_securities import MoexSecuritiesParser


class MoexParseDialog(QDialog):
    """Диалог для выбора параметров парсинга MOEX."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Параметры парсинга MOEX")
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        """Настройка UI диалога."""
        layout = QFormLayout(self)

        # Выбор банка
        self.bank_combo = QComboBox()
        self.bank_combo.addItem("Сбер", "1")
        self.bank_combo.addItem("Газпромбанк", "2")
        self.bank_combo.addItem("ВТБ", "3")
        self.bank_combo.addItem("Альфа-банк", "4")
        self.bank_combo.addItem("Т-Банк", "5")
        layout.addRow("Банк:", self.bank_combo)

        # Тип ценной бумаги (опционально, можно оставить пустым)
        self.type_combo = QComboBox()
        self.type_combo.addItem("Все типы", None)
        # Добавляем известные типы для удобства (display_name -> type_value)
        for display_name, type_value in MoexSecuritiesParser.SECURITY_TYPES.items():
            self.type_combo.addItem(display_name, type_value)
        layout.addRow("Тип бумаги (опционально):", self.type_combo)

        # Дата начала
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(datetime.now() - timedelta(days=365))
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        layout.addRow("Дата начала:", self.date_from)

        # Дата окончания
        self.date_till = QDateEdit()
        self.date_till.setCalendarPopup(True)
        self.date_till.setDate(datetime.now())
        self.date_till.setDisplayFormat("yyyy-MM-dd")
        layout.addRow("Дата окончания:", self.date_till)

        # Интервал свечей
        self.interval_combo = QComboBox()
        self.interval_combo.addItem("1 минута", 1)
        self.interval_combo.addItem("10 минут", 10)
        self.interval_combo.addItem("1 час", 60)
        self.interval_combo.addItem("1 день", 24)
        self.interval_combo.addItem("1 неделя", 7)
        self.interval_combo.addItem("1 месяц", 31)
        self.interval_combo.addItem("1 квартал", 4)
        self.interval_combo.addItem("1 год", 12)
        self.interval_combo.setCurrentIndex(3)  # По умолчанию 1 день
        layout.addRow("Интервал свечей:", self.interval_combo)

        # Кнопки
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_params(self) -> dict[str, Any]:
        """Возвращает выбранные параметры."""
        return {
            "bank_choice": self.bank_combo.currentData(),
            "security_type": self.type_combo.currentData(),
            "date_from": self.date_from.date().toString("yyyy-MM-dd"),
            "date_till": self.date_till.date().toString("yyyy-MM-dd"),
            "interval": self.interval_combo.currentData(),
        }

    def update_security_types(self, types: list[str]):
        """Обновляет список типов ценных бумаг."""
        self.type_combo.clear()
        self.type_combo.addItem("Все типы", None)
        for sec_type in types:
            display_name = MoexSecuritiesParser.TYPE_DISPLAY_NAMES.get(
                sec_type, sec_type
            )
            self.type_combo.addItem(display_name, sec_type)


class MoexSecuritySelectDialog(QDialog):
    """Диалог для выбора конкретной ценной бумаги."""

    def __init__(self, securities_df: pd.DataFrame, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор ценной бумаги")
        self.setMinimumWidth(600)
        self.securities_df = securities_df
        self.selected_security = None
        self._setup_ui()

    def _setup_ui(self):
        """Настройка UI диалога."""
        layout = QVBoxLayout(self)

        label = QLabel("Выберите ценную бумагу:")
        layout.addWidget(label)

        # Таблица с ценными бумагами
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Тикер", "Название", "Тип", "Площадка"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        # Заполняем таблицу
        self._populate_table()
        layout.addWidget(self.table)

        # Кнопки
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_table(self):
        """Заполняет таблицу данными о ценных бумагах."""
        if self.securities_df.empty:
            return

        self.table.setRowCount(len(self.securities_df))

        for row_idx, (_, row) in enumerate(self.securities_df.iterrows()):
            secid = str(row.get("secid", row.get("SECID", "")))
            shortname = str(row.get("shortname", row.get("name", "")))
            sec_type = str(row.get("type", ""))
            board = str(row.get("primary_boardid", row.get("board", "")))

            self.table.setItem(row_idx, 0, QTableWidgetItem(secid))
            self.table.setItem(row_idx, 1, QTableWidgetItem(shortname))
            self.table.setItem(row_idx, 2, QTableWidgetItem(sec_type))
            self.table.setItem(row_idx, 3, QTableWidgetItem(board))

        self.table.resizeColumnsToContents()

    def _on_accept(self):
        """Обработка нажатия OK."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Внимание", "Выберите ценную бумагу")
            return

        row_idx = selected_rows[0].row()
        self.selected_security = self.securities_df.iloc[row_idx].to_dict()
        self.accept()


async def _parse_moex_data(parser_params: dict[str, Any]) -> dict[str, Any]:
    """Выполняет парсинг данных MOEX."""
    async with MoexSecuritiesParser() as parser:
        # Получаем информацию о ценных бумагах
        bank_choice = parser_params["bank_choice"]
        bank_info = MoexSecuritiesParser.BANK_NAMES[bank_choice]
        securities_df = await parser.get_securities_info(bank_info["search"])

        if securities_df.empty:
            return {
                "error": "Не найдено ценных бумаг",
                "bank_info": bank_info,
                "securities": pd.DataFrame(),
                "candles": pd.DataFrame(),
                "charts_generated": False,
            }

        # Фильтруем по типу если указан
        security_type = parser_params.get("security_type")
        if security_type:
            securities_df = securities_df[securities_df["type"] == security_type]

        if securities_df.empty:
            return {
                "error": "Нет ценных бумаг после фильтрации",
                "bank_info": bank_info,
                "securities": securities_df,
                "candles": pd.DataFrame(),
                "charts_generated": False,
            }

        # Загружаем данные по ценным бумагам (ограничиваем для производительности)
        max_securities = 10
        all_candles_dfs = []
        processed_securities = []

        for _, row in securities_df.head(max_securities).iterrows():
            secid = row.get("secid", row.get("SECID", ""))
            shortname = row.get("shortname", row.get("name", ""))
            board = row.get("primary_boardid", row.get("board", "TQBR"))

            if not secid or (isinstance(secid, float) and pd.isna(secid)):
                continue

            board = str(board) if board and not pd.isna(board) else "TQBR"

            df = await parser.get_candles(
                secid=str(secid),
                board=board,
                date_from=parser_params.get("date_from"),
                date_till=parser_params.get("date_till"),
                interval=parser_params.get("interval", 24),
            )

            if not df.empty:
                df = parser._format_candles_dataframe(df, str(secid), str(shortname))
                all_candles_dfs.append(df)
                processed_securities.append(
                    {
                        "secid": str(secid),
                        "shortname": str(shortname),
                        "rows_count": len(df),
                    }
                )

        if all_candles_dfs:
            combined_df = pd.concat(all_candles_dfs, ignore_index=True)
            if "begin" in combined_df.columns:
                combined_df["begin"] = pd.to_datetime(combined_df["begin"])
                combined_df = combined_df.sort_values("begin").reset_index(drop=True)
        else:
            combined_df = pd.DataFrame()

        return {
            "bank_info": bank_info,
            "interval": parser_params.get("interval", 24),
            "date_from": parser_params.get("date_from"),
            "date_till": parser_params.get("date_till"),
            "securities_info": processed_securities,
            "securities": securities_df,
            "candles": combined_df,
            "charts_generated": False,
        }


class MoexChartsWidget(QWidget):
    """Виджет для отображения графиков ценных бумаг MOEX."""

    # Сигналы для уведомлений
    parse_finished = pyqtSignal(dict)  # data dict
    parse_error = pyqtSignal(str)  # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Optional[pd.DataFrame] = None
        self._parse_result: Optional[dict[str, Any]] = None
        self._theme_colors = {
            "background": "#FFFFFF",
            "text": "#000000",
            "grid": "#E0E0E0",
            "axes": "#000000",
        }
        self._setup_ui()

    def _setup_ui(self):
        """Настройка UI виджета."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Информационная панель о текущих данных (скрыта по умолчанию)
        info_layout = QHBoxLayout()
        self.info_label = QLabel("")
        # Убираем фиксированный фон, чтобы стиль адаптировался к теме
        self.info_label.setStyleSheet("padding: 5px; border-radius: 3px;")
        self.info_label.setVisible(False)  # Скрываем по умолчанию
        info_layout.addWidget(self.info_label)
        layout.addLayout(info_layout)

        # Панель управления
        control_layout = QHBoxLayout()
        self.parse_button = QPushButton("Парсить данные")
        self.parse_button.clicked.connect(self._on_parse_clicked)
        control_layout.addWidget(self.parse_button)

        control_layout.addSpacing(20)

        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems(["Цены закрытия", "OHLC", "Объемы"])
        self.chart_type_combo.currentIndexChanged.connect(self._update_charts)
        control_layout.addWidget(QLabel("Тип графика:"))
        control_layout.addWidget(self.chart_type_combo)

        control_layout.addSpacing(20)

        self.security_combo = QComboBox()
        self.security_combo.currentIndexChanged.connect(self._on_security_changed)
        control_layout.addWidget(QLabel("Ценная бумага:"))
        control_layout.addWidget(self.security_combo)

        control_layout.addStretch()

        self.export_button = QPushButton("Экспорт")
        self.export_button.clicked.connect(self._on_export_clicked)
        self.export_button.setEnabled(False)  # Включаем только когда есть данные
        control_layout.addWidget(self.export_button)

        layout.addLayout(control_layout)

        # Разделитель для графиков и таблицы
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая панель - графики (70%)
        charts_widget = QWidget()
        charts_layout = QVBoxLayout(charts_widget)
        charts_layout.setContentsMargins(0, 0, 0, 0)

        # График 1: Цены закрытия
        self.price_figure = Figure(figsize=(10, 4))
        self.price_canvas = FigureCanvas(self.price_figure)
        charts_layout.addWidget(self.price_canvas)

        # График 2: Доходность
        self.returns_figure = Figure(figsize=(10, 4))
        self.returns_canvas = FigureCanvas(self.returns_figure)
        charts_layout.addWidget(self.returns_canvas)

        splitter.addWidget(charts_widget)

        # Правая панель - таблица с данными (30%)
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.setContentsMargins(0, 0, 0, 0)

        table_label = QLabel("Данные:")
        table_layout.addWidget(table_label)

        self.data_table = QTableWidget()
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setSortingEnabled(True)
        table_layout.addWidget(self.data_table)

        splitter.addWidget(table_widget)

        # Устанавливаем соотношение 70/30 (графики/таблица)
        # setStretchFactor устанавливает пропорции: 7 для графиков, 3 для таблицы
        splitter.setStretchFactor(0, 7)  # Графики - 70%
        splitter.setStretchFactor(1, 3)  # Таблица - 30%

        layout.addWidget(splitter)

        # Начальное сообщение
        self._show_placeholder()

    def _show_placeholder(self):
        """Скрывает графики и таблицу при отсутствии данных."""
        # Очищаем фигуры без текста - просто пустые графики
        # Применяем цвет фона из темы
        self.price_figure.clear()
        self.price_figure.patch.set_facecolor(self._theme_colors["background"])
        ax = self.price_figure.add_subplot(111)
        ax.set_facecolor(self._theme_colors["background"])
        ax.axis("off")
        self.price_canvas.draw()

        self.returns_figure.clear()
        self.returns_figure.patch.set_facecolor(self._theme_colors["background"])
        ax2 = self.returns_figure.add_subplot(111)
        ax2.set_facecolor(self._theme_colors["background"])
        ax2.axis("off")
        self.returns_canvas.draw()

        self.data_table.setRowCount(0)
        self.data_table.setColumnCount(0)

        # Скрываем информационную панель
        self.info_label.setVisible(False)

    def _on_parse_clicked(self):
        """Обработчик нажатия на кнопку парсинга."""
        dialog = MoexParseDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        params = dialog.get_params()

        # Показываем прогресс
        self.parse_button.setEnabled(False)
        self.parse_button.setText("Парсинг...")

        # Запускаем асинхронный парсинг через qasync
        # qasync интегрирован с Qt event loop, можно использовать asyncio.create_task
        task = asyncio.create_task(self._parse_async(params))

    async def _parse_async(self, params: dict[str, Any]):
        """Асинхронный парсинг данных."""
        try:
            result = await _parse_moex_data(params)
            # Обновляем UI в главном потоке Qt
            if result and "error" in result and result.get("error"):
                self._on_parse_error(result["error"])
            else:
                self._on_parse_finished(result)
        except Exception as e:
            self._on_parse_error(str(e))

    def _on_parse_finished(self, result: dict[str, Any]):
        """Обработчик завершения парсинга."""
        self.parse_button.setEnabled(True)
        self.parse_button.setText("Парсить данные")

        if result.get("error"):
            QMessageBox.warning(self, "Ошибка", result["error"])
            return

        self._parse_result = result
        self._data = result.get("candles", pd.DataFrame())

        if self._data.empty:
            QMessageBox.information(self, "Информация", "Данные не найдены")
            self._show_placeholder()
            self.info_label.setVisible(False)
            self.export_button.setEnabled(False)
            return

        # Обновляем информацию о данных
        bank_name = result.get("bank_info", {}).get("display", "Неизвестно")
        records_count = len(self._data)
        securities_count = (
            len(self._data["secid"].unique()) if "secid" in self._data.columns else 1
        )
        date_from = result.get("date_from", "N/A")
        date_till = result.get("date_till", "N/A")

        # Показываем информационную панель с данными
        self.info_label.setText(
            f"Банк: {bank_name} | "
            f"Период: {date_from} - {date_till} | "
            f"Записей: {records_count} | "
            f"Ценных бумаг: {securities_count}"
        )
        self.info_label.setVisible(True)

        # Обновляем комбобокс с ценными бумагами
        self._update_security_combo()

        # Обновляем графики и таблицу
        self._update_charts()
        self._update_table()

        # Включаем кнопку экспорта
        self.export_button.setEnabled(True)

        # Эмитируем сигнал для уведомлений
        self.parse_finished.emit({
            "records": len(self._data),
            "securities": securities_count,
            "bank": bank_name
        })

    def _on_parse_error(self, error: str):
        """Обработчик ошибки парсинга."""
        self.parse_button.setEnabled(True)
        self.parse_button.setText("Парсить данные")
        # Эмитируем сигнал для уведомлений
        self.parse_error.emit(error)

    def _update_security_combo(self):
        """Обновляет комбобокс с ценными бумагами."""
        self.security_combo.clear()

        if self._data is None or self._data.empty:
            return

        # Добавляем опцию "Все" для отображения всех ценных бумаг
        self.security_combo.addItem("Все", None)

        if "secid" in self._data.columns:
            securities = sorted(self._data["secid"].unique())
            for secid in securities:
                shortname = ""
                if "shortname" in self._data.columns:
                    sec_data = self._data[self._data["secid"] == secid]
                    if not sec_data.empty:
                        shortname = sec_data["shortname"].iloc[0]
                display_text = f"{secid} ({shortname})" if shortname else secid
                self.security_combo.addItem(display_text, secid)

    def _on_security_changed(self):
        """Обработчик изменения выбранной ценной бумаги."""
        self._update_charts()
        self._update_table()

    def _update_charts(self):
        """Обновляет графики."""
        if self._data is None or self._data.empty:
            self._show_placeholder()
            return

        # Фильтруем по выбранной ценной бумаге (или показываем все)
        filtered_data = self._data.copy()
        selected_secid = self.security_combo.currentData()

        # Если выбрана конкретная ценная бумага, фильтруем
        if selected_secid is not None and "secid" in filtered_data.columns:
            filtered_data = filtered_data[filtered_data["secid"] == selected_secid]

        if filtered_data.empty:
            # Скрываем графики если нет данных
            self.price_figure.clear()
            ax = self.price_figure.add_subplot(111)
            ax.axis("off")
            self.price_canvas.draw()
            self.returns_figure.clear()
            ax2 = self.returns_figure.add_subplot(111)
            ax2.axis("off")
            self.returns_canvas.draw()
            return

        # Убеждаемся, что begin в формате datetime
        if "begin" in filtered_data.columns:
            if not pd.api.types.is_datetime64_any_dtype(filtered_data["begin"]):
                filtered_data["begin"] = pd.to_datetime(filtered_data["begin"])

        chart_type = self.chart_type_combo.currentText()

        # Получаем интервал для форматирования дат
        interval = self._parse_result.get("interval", 24) if self._parse_result else 24

        # Определяем формат оси X в зависимости от интервала
        if interval == 1:  # 1 минута
            date_format = mdates.DateFormatter("%Y-%m-%d %H:%M")
            locator = mdates.HourLocator(interval=1)
        elif interval == 10:  # 10 минут
            date_format = mdates.DateFormatter("%Y-%m-%d %H:%M")
            locator = mdates.HourLocator(interval=1)
        elif interval == 60:  # 1 час
            date_format = mdates.DateFormatter("%Y-%m-%d %H:%M")
            locator = mdates.HourLocator(interval=6)
        elif interval == 24:  # 1 день
            date_format = mdates.DateFormatter("%Y-%m-%d")
            try:
                days_span = (
                    filtered_data["begin"].max() - filtered_data["begin"].min()
                ).days
                # Адаптивный интервал: если данных много, показываем реже
                if days_span > 0:
                    locator = mdates.DayLocator(interval=max(1, days_span // 30))
                else:
                    locator = mdates.DayLocator(interval=1)
            except Exception:
                locator = mdates.DayLocator(interval=1)
        elif interval == 7:  # 1 неделя
            date_format = mdates.DateFormatter("%Y-%m-%d")
            locator = mdates.WeekLocator()
        elif interval in [31, 4, 12]:  # месяц, квартал, год
            date_format = mdates.DateFormatter("%Y-%m")
            locator = mdates.MonthLocator(interval=max(1, interval // 24))
        else:
            date_format = mdates.DateFormatter("%Y-%m-%d")
            locator = mdates.AutoDateLocator()

        # График 1: Цены закрытия / OHLC / Объемы
        self.price_figure.clear()
        # Применяем цвет фона из темы
        self.price_figure.patch.set_facecolor(self._theme_colors["background"])
        ax1 = self.price_figure.add_subplot(111)
        ax1.set_facecolor(self._theme_colors["background"])
        ax1.tick_params(colors=self._theme_colors["text"])
        ax1.xaxis.label.set_color(self._theme_colors["text"])
        ax1.yaxis.label.set_color(self._theme_colors["text"])
        ax1.title.set_color(self._theme_colors["text"])
        ax1.spines['bottom'].set_color(self._theme_colors["axes"])
        ax1.spines['top'].set_color(self._theme_colors["axes"])
        ax1.spines['right'].set_color(self._theme_colors["axes"])
        ax1.spines['left'].set_color(self._theme_colors["axes"])

        if chart_type == "Цены закрытия" and "close" in filtered_data.columns:
            # Если выбрано "Все", показываем все ценные бумаги разными линиями
            if selected_secid is None and "secid" in filtered_data.columns:
                securities = filtered_data["secid"].unique()
                for secid in securities:
                    sec_data = filtered_data[filtered_data["secid"] == secid]
                    if not sec_data.empty:
                        ax1.plot(
                            sec_data["begin"],
                            sec_data["close"],
                            label=str(secid),
                            linewidth=1.5,
                            alpha=0.7,
                        )
                ax1.legend(loc="best")
            else:
                ax1.plot(
                    filtered_data["begin"],
                    filtered_data["close"],
                    label=f"{selected_secid or 'Цена закрытия'}",
                    linewidth=1.5,
                )
            ax1.set_xlabel("Дата", fontsize=11)
            ax1.set_ylabel("Цена, RUB", fontsize=11)
            ax1.set_title("Цены закрытия", fontsize=12, fontweight="bold")
            ax1.grid(True, alpha=0.3, color=self._theme_colors["grid"])

        elif chart_type == "OHLC" and all(
            col in filtered_data.columns for col in ["open", "high", "low", "close"]
        ):
            # OHLC график (candlestick-like)
            ax1.plot(
                filtered_data["begin"],
                filtered_data["close"],
                label="Close",
                linewidth=1.5,
                color="blue",
            )
            ax1.fill_between(
                filtered_data["begin"],
                filtered_data["low"],
                filtered_data["high"],
                alpha=0.3,
                label="High-Low",
                color="gray",
            )
            ax1.plot(
                filtered_data["begin"],
                filtered_data["open"],
                "--",
                label="Open",
                linewidth=1,
                alpha=0.7,
                color="green",
            )
            ax1.set_xlabel("Дата", fontsize=11)
            ax1.set_ylabel("Цена, RUB", fontsize=11)
            ax1.set_title("OHLC (Candlestick)", fontsize=12, fontweight="bold")
            ax1.legend(loc="best")
            ax1.grid(True, alpha=0.3, color=self._theme_colors["grid"])

        elif chart_type == "Объемы" and "volume" in filtered_data.columns:
            # График объемов
            ax1.bar(
                filtered_data["begin"],
                filtered_data["volume"],
                width=0.8,
                alpha=0.7,
                color="orange",
            )
            ax1.set_xlabel("Дата", fontsize=11)
            ax1.set_ylabel("Объем", fontsize=11)
            ax1.set_title("Объемы торгов", fontsize=12, fontweight="bold")
            ax1.grid(True, alpha=0.3, color=self._theme_colors["grid"])
        else:
            # Если нет данных для выбранного типа - просто пустой график
            ax1.axis("off")

        # Применяем форматирование оси X
        ax1.xaxis.set_major_formatter(date_format)
        ax1.xaxis.set_major_locator(locator)
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right")
        self.price_figure.tight_layout()
        self.price_canvas.draw()

        # График 2: Доходность (всегда показываем для выбранной бумаги)
        self.returns_figure.clear()
        # Применяем цвет фона из темы
        self.returns_figure.patch.set_facecolor(self._theme_colors["background"])
        ax2 = self.returns_figure.add_subplot(111)
        ax2.set_facecolor(self._theme_colors["background"])
        ax2.tick_params(colors=self._theme_colors["text"])
        ax2.xaxis.label.set_color(self._theme_colors["text"])
        ax2.yaxis.label.set_color(self._theme_colors["text"])
        ax2.title.set_color(self._theme_colors["text"])
        ax2.spines['bottom'].set_color(self._theme_colors["axes"])
        ax2.spines['top'].set_color(self._theme_colors["axes"])
        ax2.spines['right'].set_color(self._theme_colors["axes"])
        ax2.spines['left'].set_color(self._theme_colors["axes"])

        if "close" in filtered_data.columns and len(filtered_data) > 1:
            # Если выбрано "Все", показываем доходность для первой бумаги
            data_for_returns = filtered_data
            if selected_secid is None and "secid" in filtered_data.columns:
                # Берем первую ценную бумагу для расчета доходности
                first_secid = filtered_data["secid"].iloc[0]
                data_for_returns = filtered_data[filtered_data["secid"] == first_secid]

            if not data_for_returns.empty and len(data_for_returns) > 1:
                returns = data_for_returns["close"].pct_change()
                secid_label = (
                    data_for_returns["secid"].iloc[0]
                    if "secid" in data_for_returns.columns
                    else ""
                )
                ax2.plot(
                    data_for_returns["begin"],
                    returns,
                    linewidth=1.5,
                    color="green",
                    label=f"Доходность {secid_label}",
                )
                ax2.axhline(0, color="black", linewidth=0.8, linestyle="--")
                ax2.set_xlabel("Дата", fontsize=11)
                ax2.set_ylabel("Доходность", fontsize=11)
                ax2.set_title(
                    "Доходность по цене закрытия", fontsize=12, fontweight="bold"
                )
                ax2.legend(loc="best")
                ax2.grid(True, alpha=0.3, color=self._theme_colors["grid"])

                # Применяем форматирование оси X
                ax2.xaxis.set_major_formatter(date_format)
                ax2.xaxis.set_major_locator(locator)
                plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")

        self.returns_figure.tight_layout()
        self.returns_canvas.draw()

    def update_theme_colors(self, theme_colors: dict):
        """
        Обновляет цвета графиков в соответствии с темой.
        
        Args:
            theme_colors: Словарь с цветами темы (background, text, grid, axes)
        """
        self._theme_colors = theme_colors
        # Обновляем графики, если они уже отображены
        if self._data is not None and not self._data.empty:
            self._update_charts()
        else:
            # Если данных нет, обновляем фон placeholder'ов
            self._show_placeholder()

    def _update_table(self):
        """Обновляет таблицу с данными."""
        if self._data is None or self._data.empty:
            self.data_table.setRowCount(0)
            self.data_table.setColumnCount(0)
            return

        # Фильтруем по выбранной ценной бумаге (или показываем все)
        filtered_data = self._data.copy()
        selected_secid = self.security_combo.currentData()

        # Если выбрана конкретная ценная бумага, фильтруем
        if selected_secid is not None and "secid" in filtered_data.columns:
            filtered_data = filtered_data[filtered_data["secid"] == selected_secid]

        # Ограничиваем количество строк для производительности (показываем последние 1000)
        if len(filtered_data) > 1000:
            filtered_data = filtered_data.tail(1000)

        # Выбираем колонки для отображения
        display_columns = ["begin", "close", "open", "high", "low", "volume"]
        if "secid" in filtered_data.columns:
            display_columns.insert(0, "secid")
        if "shortname" in filtered_data.columns:
            display_columns.insert(1, "shortname")

        # Фильтруем только существующие колонки
        display_columns = [
            col for col in display_columns if col in filtered_data.columns
        ]

        self.data_table.setColumnCount(len(display_columns))
        self.data_table.setHorizontalHeaderLabels(display_columns)
        self.data_table.setRowCount(len(filtered_data))

        for row_idx, (_, row) in enumerate(filtered_data.iterrows()):
            for col_idx, col_name in enumerate(display_columns):
                value = row[col_name]
                # Обрабатываем разные типы значений
                if pd.api.types.is_datetime64_any_dtype(type(value)) or isinstance(
                    value, pd.Timestamp
                ):
                    if pd.isna(value):
                        item = QTableWidgetItem("N/A")
                    else:
                        item = QTableWidgetItem(value.strftime("%Y-%m-%d %H:%M:%S"))
                elif isinstance(value, (int, float)):
                    if pd.isna(value):
                        item = QTableWidgetItem("N/A")
                    else:
                        # Форматируем числа: для объема используем целое число, для цен - 2 знака
                        if col_name == "volume":
                            item = QTableWidgetItem(f"{int(value):,}".replace(",", " "))
                        else:
                            item = QTableWidgetItem(
                                f"{value:.2f}"
                                if isinstance(value, float)
                                else str(value)
                            )
                else:
                    str_value = str(value) if not pd.isna(value) else "N/A"
                    item = QTableWidgetItem(str_value)
                self.data_table.setItem(row_idx, col_idx, item)

        self.data_table.resizeColumnsToContents()

    def _on_export_clicked(self):
        """Обработчик экспорта данных."""
        if self._data is None or self._data.empty:
            QMessageBox.warning(self, "Внимание", "Нет данных для экспорта")
            return

        from PyQt6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить данные",
            "",
            "CSV Files (*.csv);;Excel Files (*.xlsx)",
        )

        if file_path:
            try:
                if file_path.endswith(".xlsx"):
                    try:
                        self._data.to_excel(file_path, index=False, engine="openpyxl")
                        QMessageBox.information(
                            self, "Успех", "Данные успешно экспортированы в Excel"
                        )
                    except ImportError:
                        QMessageBox.warning(
                            self,
                            "Внимание",
                            "Для экспорта в Excel требуется библиотека openpyxl. Экспортируем в CSV.",
                        )
                        csv_path = file_path.replace(".xlsx", ".csv")
                        self._data.to_csv(csv_path, index=False, encoding="utf-8-sig")
                        QMessageBox.information(
                            self, "Успех", "Данные успешно экспортированы в CSV"
                        )
                else:
                    self._data.to_csv(file_path, index=False, encoding="utf-8-sig")
                    QMessageBox.information(
                        self, "Успех", "Данные успешно экспортированы"
                    )
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка экспорта: {e}")
