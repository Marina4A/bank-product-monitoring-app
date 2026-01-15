"""
Виджет для отображения рейтингов банков с сайта Banki.ru.

Отображает таблицу рейтингов банков с возможностью парсинга данных
и фильтрации по различным показателям и датам.
"""

import asyncio
from typing import Any, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QFrame,
    QMessageBox,
    QProgressBar,
)

from core.parsers.banki_ratings import BankiRatingsParser


class NumericTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem, который сортируется как число."""
    
    def __init__(self, text: str, value: int):
        super().__init__(text)
        self._numeric_value = value
    
    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return self._numeric_value < other._numeric_value
        return super().__lt__(other)


class BankiRatingsWidget(QWidget):
    """Виджет для отображения рейтингов банков Banki.ru."""

    # Сигналы
    parse_started = pyqtSignal()
    parse_finished = pyqtSignal(dict)  # data dict
    parse_error = pyqtSignal(str)  # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ratings_data: Optional[dict[str, Any]] = None
        self._all_ratings: list[dict[str, Any]] = []  # Все загруженные рейтинги
        self._parsing_in_progress = False  # Флаг для предотвращения одновременного парсинга
        self._setup_ui()

    def _setup_ui(self):
        """Настройка UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Заголовок и информация
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.Shape.StyledPanel)
        header_layout = QVBoxLayout(header_frame)

        title_label = QLabel("Рейтинги банков (Banki.ru)")
        title_font = title_label.font()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)

        self.metadata_label = QLabel("Выберите параметры и запустите парсинг")
        self.metadata_label.setWordWrap(True)
        header_layout.addWidget(self.metadata_label)

        layout.addWidget(header_frame)

        # Панель управления парсингом
        control_frame = QFrame()
        control_frame.setFrameShape(QFrame.Shape.StyledPanel)
        control_layout = QHBoxLayout(control_frame)

        # Кнопка парсинга
        self.parse_button = QPushButton("Парсить рейтинги")
        self.parse_button.clicked.connect(self._on_parse_clicked)
        control_layout.addWidget(self.parse_button)

        control_layout.addSpacing(20)

        # Фильтр по месту в рейтинге
        control_layout.addWidget(QLabel("Фильтр по месту:"))
        self.place_filter_min = QComboBox()
        self.place_filter_min.setEditable(True)
        self.place_filter_min.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.place_filter_min.lineEdit().setPlaceholderText("От")
        self.place_filter_min.lineEdit().setValidator(QIntValidator(1, 10000, self))
        self.place_filter_min.lineEdit().textChanged.connect(self._on_place_filter_changed)
        control_layout.addWidget(self.place_filter_min)

        control_layout.addWidget(QLabel("—"))

        self.place_filter_max = QComboBox()
        self.place_filter_max.setEditable(True)
        self.place_filter_max.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.place_filter_max.lineEdit().setPlaceholderText("До")
        self.place_filter_max.lineEdit().setValidator(QIntValidator(1, 10000, self))
        self.place_filter_max.lineEdit().textChanged.connect(self._on_place_filter_changed)
        control_layout.addWidget(self.place_filter_max)

        control_layout.addSpacing(20)

        # Показатель (индикатор)
        control_layout.addWidget(QLabel("Показатель:"))
        self.indicator_combo = QComboBox()
        # Маппинг показателей на PROPERTY_ID из HTML структуры
        self.indicator_map = {
            "Активы нетто": "",  # По умолчанию (PROPERTY_ID=10 или пустой)
            "Чистая прибыль": "30",
            "Капитал (по форме 123)": "25",
            "Капитал (по форме 134)": "20",
            "Кредитный портфель": "40",
            "Вклады физических лиц": "60",
        }
        self.indicator_combo.addItems(list(self.indicator_map.keys()))
        control_layout.addWidget(self.indicator_combo)

        control_layout.addSpacing(20)

        # Период - выбор месяца и года (данные на конец выбранного месяца)
        control_layout.addWidget(QLabel("Период:"))
        self.date_combo = QComboBox()
        self._populate_month_combo(self.date_combo)
        control_layout.addWidget(self.date_combo)

        control_layout.addStretch()

        layout.addWidget(control_frame)

        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # Неопределенный прогресс
        layout.addWidget(self.progress_bar)

        # Таблица рейтингов
        self.ratings_table = QTableWidget()
        self.ratings_table.setColumnCount(7)
        self.ratings_table.setHorizontalHeaderLabels([
            "Место",
            "Банк",
            "Лицензия",
            "Регион",
            "Значение (руб.)",
            "Изменение (руб.)",
            "Изменение (%)",
        ])
        self.ratings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ratings_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.ratings_table.setAlternatingRowColors(True)

        # Скрываем вертикальный заголовок (индекс строки)
        self.ratings_table.verticalHeader().setVisible(False)

        # Настройка заголовков таблицы
        header = self.ratings_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Банк растягивается
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Регион по содержимому
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Значения по содержимому
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        # Включаем сортировку
        self.ratings_table.setSortingEnabled(True)

        # Подключаем сигнал сортировки для обработки
        header.sectionClicked.connect(self._on_header_clicked)

        layout.addWidget(self.ratings_table)

        # Статистика
        stats_frame = QFrame()
        stats_frame.setFrameShape(QFrame.Shape.StyledPanel)
        stats_layout = QHBoxLayout(stats_frame)

        self.stats_label = QLabel("Всего банков: 0")
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()

        layout.addWidget(stats_frame)

    def _populate_month_combo(self, combo: QComboBox):
        """
        Заполняет ComboBox месяцами и годами, как на сайте Banki.ru.

        Args:
            combo: QComboBox для заполнения
        """
        from datetime import datetime
        today = datetime.now()

        # Генерируем список месяцев от текущего до 2012 года
        months_ru = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]

        items = []
        current_year = today.year
        current_month = today.month

        # Генерируем все месяцы от текущего до 2012 года
        # Для удобства пользователя: сначала более поздние даты (сверху), потом более ранние
        for year in range(current_year, 2011, -1):  # От текущего года к 2012
            start_month = current_month if year == current_year else 12
            end_month = 1
            for month in range(start_month, end_month - 1, -1):  # От текущего/12 месяца к 1
                month_name = months_ru[month - 1]
                date_value = f"{year}-{month:02d}-01"
                display_text = f"{month_name} {year}"  # Формат как на сайте: "Декабрь 2025"
                items.append((display_text, date_value))

        # Добавляем элементы в ComboBox
        for display_text, date_value in items:
            combo.addItem(display_text, date_value)

        # Устанавливаем значение по умолчанию - текущий месяц
        default_value = f"{current_year}-{current_month:02d}-01"

        # Находим индекс по умолчанию
        for i in range(combo.count()):
            if combo.itemData(i) == default_value:
                combo.setCurrentIndex(i)
                break

    def _on_parse_clicked(self):
        """Обработчик нажатия на кнопку парсинга."""
        # Формируем URL на основе параметров
        # date1 - выбранный период (месяц и год, данные на конец месяца)
        # date2 - предыдущий месяц (автоматически для сравнения)
        from datetime import datetime

        date1_value = self.date_combo.currentData()  # Выбранный период

        # Вычисляем date2 (предыдущий месяц) для сравнения
        # Парсим дату из формата "YYYY-MM-01"
        date1_parts = date1_value.split("-")
        year = int(date1_parts[0])
        month = int(date1_parts[1])

        # Вычисляем предыдущий месяц
        if month == 1:
            prev_year = year - 1
            prev_month = 12
        else:
            prev_year = year
            prev_month = month - 1

        date2_str = f"{prev_year}-{prev_month:02d}-01"
        date1_str = date1_value

        # Получаем PROPERTY_ID из маппинга
        indicator = self.indicator_combo.currentText()
        property_id = self.indicator_map.get(indicator, "")

        base_url = "https://www.banki.ru/banks/ratings/"
        if property_id:
            url = f"{base_url}?sort_param=bankname&PROPERTY_ID={property_id}&date1={date1_str}&date2={date2_str}"
        else:
            # Для "Активы нетто" PROPERTY_ID не указывается (по умолчанию)
            url = f"{base_url}?sort_param=bankname&date1={date1_str}&date2={date2_str}"

        # Проверяем, не идет ли уже парсинг
        if self._parsing_in_progress:
            QMessageBox.warning(self, "Внимание", "Парсинг уже выполняется. Дождитесь завершения.")
            return

        # Показываем прогресс
        self.parse_button.setEnabled(False)
        self.parse_button.setText("Парсинг...")
        self.progress_bar.setVisible(True)
        self.metadata_label.setText(f"Парсинг рейтингов...")

        # Очищаем таблицу
        self.ratings_table.setRowCount(0)

        # Эмитируем сигнал начала парсинга
        self.parse_started.emit()

        # Запускаем асинхронный парсинг через qasync
        # qasync интегрирован с Qt event loop, можно использовать asyncio.create_task
        # Но нужно убедиться, что мы не создаем несколько задач одновременно
        self._parsing_in_progress = True
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Если loop уже запущен (что обычно так и есть с qasync), создаем задачу
                asyncio.create_task(self._parse_async(url))
            else:
                # Если loop не запущен (не должно происходить с qasync), запускаем его
                loop.run_until_complete(self._parse_async(url))
        except RuntimeError as e:
            # Если нет event loop или другая ошибка, логируем и показываем ошибку
            print(f"Ошибка при создании задачи: {e}")
            self._parsing_in_progress = False
            self.parse_button.setEnabled(True)
            self.parse_button.setText("Парсить рейтинги")
            self.progress_bar.setVisible(False)
            QMessageBox.critical(self, "Ошибка", f"Не удалось запустить парсинг: {e}")

    async def _parse_async(self, url: str):
        """Асинхронный парсинг данных."""
        try:
            async with BankiRatingsParser(headless=True) as parser:
                data = await parser.parse_page(url)
                self._ratings_data = data
            
            # Небольшая задержка после закрытия парсера для завершения всех внутренних задач Playwright
            # Это предотвращает RuntimeError при обновлении UI
            await asyncio.sleep(0.3)
            
            # Обновляем UI в главном потоке через QTimer
            # Это гарантирует выполнение в главном потоке Qt и предотвращает конфликты с Playwright
            QTimer.singleShot(0, lambda: self._update_ui_with_data(data))

            # Эмитируем сигнал завершения парсинга
            QTimer.singleShot(0, lambda: self.parse_finished.emit(data))

        except Exception as e:
            error_msg = f"Ошибка при парсинге: {str(e)}"
            print(f"Ошибка: {error_msg}")
            import traceback
            traceback.print_exc()

            # Небольшая задержка перед обновлением UI
            await asyncio.sleep(0.3)

            # Обновляем UI в главном потоке через QTimer
            QTimer.singleShot(0, lambda: self._show_error(error_msg))

            # Эмитируем сигнал ошибки
            QTimer.singleShot(0, lambda: self.parse_error.emit(error_msg))

        finally:
            # Сбрасываем флаг парсинга
            self._parsing_in_progress = False
            
            # Обновляем UI в главном потоке через QTimer
            def update_ui_after_parsing():
                self.parse_button.setEnabled(True)
                self.parse_button.setText("Парсить рейтинги")
                self.progress_bar.setVisible(False)
            
            QTimer.singleShot(0, update_ui_after_parsing)

    def _update_ui_with_data(self, data: dict[str, Any]):
        """Обновляет UI с полученными данными."""
        # Обновляем метаданные
        metadata = data.get('metadata', {})
        metadata_text = "Рейтинги банков"

        if metadata.get('indicator'):
            metadata_text += f" | Показатель: {metadata['indicator']}"
        # Отображаем выбранный период (date1 - основной период)
        if metadata.get('date1'):
            date_display = metadata['date1'].get('display', metadata['date1'].get('value', ''))
            metadata_text += f" | Период: {date_display}"
        if metadata.get('region'):
            metadata_text += f" | Регион: {metadata['region']}"

        total_banks = data.get('total_banks', 0)
        metadata_text += f" | Всего банков: {total_banks} | Страниц: {data.get('total_pages', 0)}"

        self.metadata_label.setText(metadata_text)

        # Сохраняем все рейтинги для фильтрации
        self._all_ratings = data.get('ratings', [])

        # Применяем фильтрацию и отображаем данные
        self._apply_filters_and_display()
        
        # Сигнал parse_finished уже эмитируется в _parse_async, не нужно дублировать

    def _on_header_clicked(self, column: int):
        """Обработчик клика по заголовку колонки."""
        # Сортировка уже включена через setSortingEnabled(True)
        # Этот метод может быть использован для дополнительной логики
        pass

    def _on_place_filter_changed(self):
        """Обработчик изменения фильтра по месту в рейтинге."""
        if self._all_ratings:
            self._apply_filters_and_display()

    def _apply_filters_and_display(self):
        """Применяет фильтры к данным и отображает результат."""
        # Фильтруем по месту в рейтинге
        filtered_ratings = self._all_ratings.copy()

        # Получаем значения фильтров
        min_place_text = self.place_filter_min.lineEdit().text().strip()
        max_place_text = self.place_filter_max.lineEdit().text().strip()
        
        min_place = None
        max_place = None
        
        if min_place_text:
            try:
                min_place = int(min_place_text)
            except (ValueError, TypeError):
                pass

        if max_place_text:
            try:
                max_place = int(max_place_text)
            except (ValueError, TypeError):
                pass

        # Применяем оба фильтра одновременно для корректной работы
        if min_place is not None or max_place is not None:
            filtered_ratings = [
                r for r in filtered_ratings
                if r.get('place') is not None
                and (min_place is None or int(r.get('place')) >= min_place)
                and (max_place is None or int(r.get('place')) <= max_place)
            ]

        # Отображаем отфильтрованные данные
        self._display_ratings(filtered_ratings)

    def _display_ratings(self, ratings: list[dict[str, Any]]):
        """Отображает список рейтингов в таблице."""
        self.ratings_table.setRowCount(len(ratings))

        for row, rating in enumerate(ratings):
            # Место в рейтинге (только число, целое) - используем NumericTableWidgetItem для правильной сортировки
            place_value = rating.get('place', 0)
            if place_value:
                place_int = int(place_value)
                place_text = str(place_int)
            else:
                place_int = 0
                place_text = ""
            place_item = NumericTableWidgetItem(place_text, place_int)
            self.ratings_table.setItem(row, 0, place_item)

            # Название банка
            bank_name = rating.get('bank_name', '')
            bank_item = QTableWidgetItem(bank_name)
            if rating.get('bank_link'):
                bank_item.setToolTip(f"Ссылка: {rating['bank_link']}")
            self.ratings_table.setItem(row, 1, bank_item)

            # Лицензия
            license_item = QTableWidgetItem(rating.get('license_number', ''))
            self.ratings_table.setItem(row, 2, license_item)

            # Регион
            region_item = QTableWidgetItem(rating.get('region', ''))
            self.ratings_table.setItem(row, 3, region_item)

            # Значение (руб.) - оставляем как есть, только с разделителями тысяч
            value_date1 = rating.get('value_date1')
            if value_date1 is not None:
                value_date1_text = self._format_value_rub(value_date1)
                value_date1_item = QTableWidgetItem(value_date1_text)
                # Для сортировки используем числовое значение
                value_date1_item.setData(Qt.ItemDataRole.UserRole, float(value_date1))
                self.ratings_table.setItem(row, 4, value_date1_item)
            else:
                empty_item = QTableWidgetItem("")
                empty_item.setData(Qt.ItemDataRole.UserRole, 0.0)
                self.ratings_table.setItem(row, 4, empty_item)

            # Изменение (руб.) - форматируем как +1 250 801 (без сокращений)
            change_abs = rating.get('change_absolute')
            if change_abs is not None:
                change_abs_text = self._format_change_rub(change_abs)
                change_abs_item = QTableWidgetItem(change_abs_text)
                # Для сортировки используем числовое значение
                change_abs_item.setData(Qt.ItemDataRole.UserRole, float(change_abs))
                # Цвет в зависимости от типа изменения
                if rating.get('change_type') == 'increase':
                    change_abs_item.setForeground(QColor(60, 179, 113))  # Зеленый
                elif rating.get('change_type') == 'decrease':
                    change_abs_item.setForeground(QColor(220, 20, 60))  # Красный
                self.ratings_table.setItem(row, 5, change_abs_item)
            else:
                empty_item = QTableWidgetItem("")
                empty_item.setData(Qt.ItemDataRole.UserRole, 0.0)
                self.ratings_table.setItem(row, 5, empty_item)

            # Изменение (%) - из поля change_percent
            change_percent = rating.get('change_percent')
            if change_percent is not None:
                change_percent_text = f"{change_percent:+.2f}%"
                change_percent_item = QTableWidgetItem(change_percent_text)
                # Для сортировки используем числовое значение
                change_percent_item.setData(Qt.ItemDataRole.UserRole, float(change_percent))
                # Цвет в зависимости от типа изменения
                if rating.get('change_type') == 'increase':
                    change_percent_item.setForeground(QColor(60, 179, 113))  # Зеленый
                elif rating.get('change_type') == 'decrease':
                    change_percent_item.setForeground(QColor(220, 20, 60))  # Красный
                self.ratings_table.setItem(row, 6, change_percent_item)
            else:
                empty_item = QTableWidgetItem("")
                empty_item.setData(Qt.ItemDataRole.UserRole, 0.0)
                self.ratings_table.setItem(row, 6, empty_item)

        # Автоматически изменяем высоту строк
        self.ratings_table.resizeRowsToContents()

        # Сортируем по месту в рейтинге (по умолчанию)
        self.ratings_table.sortItems(0, Qt.SortOrder.AscendingOrder)

        # Обновляем статистику (показываем количество отфильтрованных записей)
        filtered_count = len(ratings)
        total_count = len(self._all_ratings)
        if filtered_count < total_count:
            self.stats_label.setText(f"Показано банков: {filtered_count} из {total_count}")
        else:
            self.stats_label.setText(f"Всего банков: {total_count}")

    def _show_error(self, error_msg: str):
        """Показывает ошибку в UI."""
        self.metadata_label.setText(f"Ошибка: {error_msg}")
        self.ratings_table.setRowCount(0)
        self.stats_label.setText("Всего банков: 0")
        self._all_ratings = []  # Очищаем данные при ошибке

        # Показываем диалог с ошибкой
        QMessageBox.critical(self, "Ошибка парсинга", error_msg)

    def _format_value_rub(self, value: float) -> str:
        """
        Форматирует значение в рублях для отображения (без сокращений, только разделители тысяч).

        Args:
            value: Числовое значение в рублях

        Returns:
            Отформатированная строка (например, "335 388 454")
        """
        if value is None:
            return ""

        try:
            # Округляем до целого и форматируем с разделителями тысяч
            formatted = f"{int(round(value)):,}".replace(',', ' ')
            return formatted
        except Exception:
            return str(int(value)) if value is not None else ""

    def _format_change_rub(self, value: float) -> str:
        """
        Форматирует изменение в рублях для отображения (с знаком, без сокращений).

        Args:
            value: Числовое значение изменения в рублях

        Returns:
            Отформатированная строка (например, "+1 250 801" или "-500 000")
        """
        if value is None:
            return ""

        try:
            # Округляем до целого и форматируем с разделителями тысяч
            abs_value = abs(value)
            formatted = f"{int(round(abs_value)):,}".replace(',', ' ')

            # Добавляем знак
            if value < 0:
                formatted = f"-{formatted}"
            elif value > 0:
                formatted = f"+{formatted}"
            # Если value == 0, оставляем без знака

            return formatted
        except Exception:
            return str(int(value)) if value is not None else ""
