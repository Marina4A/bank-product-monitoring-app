"""
Виджет для отображения рейтингов банков с сайта Banki.ru.

Отображает таблицу рейтингов банков с возможностью парсинга данных
и фильтрации по различным показателям и датам.
"""

import asyncio
import re
from typing import Any, Optional

from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QColor, QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
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
    """Элемент таблицы для числовой сортировки."""

    def __lt__(self, other):
        """Переопределяем сравнение для числовой сортировки."""
        if isinstance(other, NumericTableWidgetItem):
            self_value = self.data(Qt.ItemDataRole.UserRole)
            other_value = other.data(Qt.ItemDataRole.UserRole)
            try:
                return float(self_value or 0) < float(other_value or 0)
            except (ValueError, TypeError):
                return super().__lt__(other)
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

        title_label = QLabel("Рейтинги банков")
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
        # Используем textChanged от lineEdit() вместо currentTextChanged для редактируемого QComboBox
        # Это гарантирует, что сигнал срабатывает только при изменении введенного текста
        self.place_filter_min.lineEdit().textChanged.connect(self._on_place_filter_changed)
        control_layout.addWidget(self.place_filter_min)

        control_layout.addWidget(QLabel("—"))

        self.place_filter_max = QComboBox()
        self.place_filter_max.setEditable(True)
        self.place_filter_max.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.place_filter_max.lineEdit().setPlaceholderText("До")
        self.place_filter_max.lineEdit().setValidator(QIntValidator(1, 10000, self))
        # Используем textChanged от lineEdit() вместо currentTextChanged для редактируемого QComboBox
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

        # Дата 1 (начальная)
        control_layout.addWidget(QLabel("Дата 1:"))
        self.date1_edit = QDateEdit()
        self.date1_edit.setCalendarPopup(True)
        # Устанавливаем дату по умолчанию (декабрь 2025)
        default_date1 = QDate(2025, 12, 1)
        self.date1_edit.setDate(default_date1)
        self.date1_edit.setDisplayFormat("dd.MM.yyyy")
        control_layout.addWidget(self.date1_edit)

        # Дата 2 (конечная)
        control_layout.addWidget(QLabel("Дата 2:"))
        self.date2_edit = QDateEdit()
        self.date2_edit.setCalendarPopup(True)
        # Устанавливаем дату по умолчанию (ноябрь 2025)
        default_date2 = QDate(2025, 11, 1)
        self.date2_edit.setDate(default_date2)
        self.date2_edit.setDisplayFormat("dd.MM.yyyy")
        control_layout.addWidget(self.date2_edit)

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

    def _on_parse_clicked(self):
        """Обработчик нажатия на кнопку парсинга."""
        # Формируем URL на основе параметров
        date1_str = self.date1_edit.date().toString("yyyy-MM-dd")
        date2_str = self.date2_edit.date().toString("yyyy-MM-dd")

        # Получаем PROPERTY_ID из маппинга
        indicator = self.indicator_combo.currentText()
        property_id = self.indicator_map.get(indicator, "")

        base_url = "https://www.banki.ru/banks/ratings/"
        if property_id:
            url = f"{base_url}?sort_param=bankname&PROPERTY_ID={property_id}&date1={date1_str}&date2={date2_str}"
        else:
            # Для "Активы нетто" PROPERTY_ID не указывается (по умолчанию)
            url = f"{base_url}?sort_param=bankname&date1={date1_str}&date2={date2_str}"

        # Показываем прогресс
        self.parse_button.setEnabled(False)
        self.parse_button.setText("Парсинг...")
        self.progress_bar.setVisible(True)
        # self.metadata_label.setText(f"Парсинг рейтингов... URL: {url}")

        # Очищаем таблицу
        self.ratings_table.setRowCount(0)

        # Эмитируем сигнал начала парсинга
        self.parse_started.emit()

        # Запускаем асинхронный парсинг
        asyncio.create_task(self._parse_async(url))

    async def _parse_async(self, url: str):
        """Асинхронный парсинг данных."""
        try:
            async with BankiRatingsParser(headless=True) as parser:
                data = await parser.parse_page(url)
                self._ratings_data = data

                # Обновляем UI в главном потоке через qasync
                self._update_ui_with_data(data)

                # Эмитируем сигнал завершения парсинга
                self.parse_finished.emit(data)

        except Exception as e:
            error_msg = f"Ошибка при парсинге: {str(e)}"
            print(f"Ошибка: {error_msg}")
            import traceback
            traceback.print_exc()

            # Обновляем UI в главном потоке
            self._show_error(error_msg)

            # Эмитируем сигнал ошибки
            self.parse_error.emit(error_msg)

        finally:
            # Восстанавливаем кнопку и скрываем прогресс
            self.parse_button.setEnabled(True)
            self.parse_button.setText("Парсить рейтинги")
            self.progress_bar.setVisible(False)

    def _update_ui_with_data(self, data: dict[str, Any]):
        """Обновляет UI с полученными данными."""
        # Обновляем метаданные
        metadata = data.get('metadata', {})
        metadata_text = "Рейтинги банков"

        if metadata.get('indicator'):
            metadata_text += f" | Показатель: {metadata['indicator']}"
        if metadata.get('date1'):
            date1_display = metadata['date1'].get('display', metadata['date1'].get('value', ''))
            metadata_text += f" | Дата 1: {date1_display}"
        if metadata.get('date2'):
            date2_display = metadata['date2'].get('display', metadata['date2'].get('value', ''))
            metadata_text += f" | Дата 2: {date2_display}"
        if metadata.get('region'):
            metadata_text += f" | Регион: {metadata['region']}"

        metadata_text += f" | Всего банков: {data.get('total_banks', 0)} | Страниц: {data.get('total_pages', 0)}"

        self.metadata_label.setText(metadata_text)

        # Сохраняем все рейтинги для фильтрации
        self._all_ratings = data.get('ratings', [])

        # Применяем фильтрацию и отображаем данные
        self._apply_filters_and_display()

    def _on_header_clicked(self, column: int):
        """Обработчик клика по заголовку колонки."""
        # Сортировка уже включена через setSortingEnabled(True)
        # Этот метод может быть использован для дополнительной логики
        pass

    def _on_place_filter_changed(self, text: str = ""):
        """Обработчик изменения фильтра по месту в рейтинге."""
        # Сигнал textChanged от lineEdit() срабатывает при изменении текста
        # text - это новый текст, но мы все равно используем lineEdit().text() для надежности
        if self._all_ratings:
            self._apply_filters_and_display()

    def _apply_filters_and_display(self):
        """Применяет фильтры к данным и отображает результат."""
        # Получаем значения фильтров из полей ввода
        # Используем lineEdit().text() для получения введенного текста, а не currentText()
        # currentText() возвращает текст выбранного элемента из списка, а не введенный текст
        min_place_text = self.place_filter_min.lineEdit().text().strip()
        min_place = None
        if min_place_text:
            try:
                min_place = int(min_place_text)
                # Убеждаемся, что значение валидно
                if min_place < 1:
                    min_place = None
            except ValueError:
                min_place = None

        max_place_text = self.place_filter_max.lineEdit().text().strip()
        max_place = None
        if max_place_text:
            try:
                max_place = int(max_place_text)
                # Убеждаемся, что значение валидно
                if max_place < 1:
                    max_place = None
            except ValueError:
                max_place = None

        # Если фильтры не заданы, показываем все данные
        if min_place is None and max_place is None:
            filtered_ratings = self._all_ratings.copy()
        else:
            # Применяем фильтры
            filtered_ratings = []
            for r in self._all_ratings:
                place = r.get('place')
                # Пропускаем записи без места в рейтинге
                if place is None:
                    continue
                
                # Преобразуем place в int, если это не int
                # Убеждаемся, что place - это число, а не строка
                try:
                    if isinstance(place, str):
                        # Убираем все нецифровые символы из начала строки
                        place_clean = place.strip()
                        # Извлекаем первое число из строки
                        match = re.search(r'\d+', place_clean)
                        if match:
                            place_int = int(match.group())
                        else:
                            continue
                    elif isinstance(place, (int, float)):
                        place_int = int(place)
                    else:
                        continue
                except (ValueError, TypeError):
                    continue
                
                # Применяем фильтры: место должно быть >= min_place И <= max_place
                # Проверяем каждый фильтр отдельно
                if min_place is not None:
                    if place_int < min_place:
                        continue
                if max_place is not None:
                    if place_int > max_place:
                        continue
                
                filtered_ratings.append(r)

        # Отображаем отфильтрованные данные
        self._display_ratings(filtered_ratings)

    def _display_ratings(self, ratings: list[dict[str, Any]]):
        """Отображает список рейтингов в таблице."""
        self.ratings_table.setRowCount(len(ratings))

        for row, rating in enumerate(ratings):
            # Место в рейтинге (только число, целое) - используем NumericTableWidgetItem для правильной сортировки
            place_value = rating.get('place', 0)
            place_text = str(int(place_value)) if place_value else ""
            place_item = NumericTableWidgetItem(place_text)
            # Для сортировки используем целое число
            place_item.setData(Qt.ItemDataRole.UserRole, int(place_value) if place_value else 0)
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

            # Значение (руб.) - оставляем как есть, только с разделителями тысяч - используем NumericTableWidgetItem для правильной сортировки
            value_date1 = rating.get('value_date1')
            if value_date1 is not None:
                value_date1_text = self._format_value_rub(value_date1)
                value_date1_item = NumericTableWidgetItem(value_date1_text)
                # Для сортировки используем числовое значение
                value_date1_item.setData(Qt.ItemDataRole.UserRole, float(value_date1))
                self.ratings_table.setItem(row, 4, value_date1_item)
            else:
                empty_item = NumericTableWidgetItem("")
                empty_item.setData(Qt.ItemDataRole.UserRole, 0.0)
                self.ratings_table.setItem(row, 4, empty_item)

            # Изменение (руб.) - форматируем как +1 250 801 (без сокращений) - используем NumericTableWidgetItem для правильной сортировки
            change_abs = rating.get('change_absolute')
            if change_abs is not None:
                change_abs_text = self._format_change_rub(change_abs)
                change_abs_item = NumericTableWidgetItem(change_abs_text)
                # Для сортировки используем числовое значение
                change_abs_item.setData(Qt.ItemDataRole.UserRole, float(change_abs))
                # Цвет в зависимости от типа изменения
                if rating.get('change_type') == 'increase':
                    change_abs_item.setForeground(QColor(60, 179, 113))  # Зеленый
                elif rating.get('change_type') == 'decrease':
                    change_abs_item.setForeground(QColor(220, 20, 60))  # Красный
                self.ratings_table.setItem(row, 5, change_abs_item)
            else:
                empty_item = NumericTableWidgetItem("")
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
