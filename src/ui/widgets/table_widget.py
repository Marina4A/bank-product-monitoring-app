from typing import List, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import BankProduct, Filters


class TableWidget(QWidget):
    """Виджет таблицы с продуктами."""

    # Сигналы
    refresh_requested = pyqtSignal()
    export_requested = pyqtSignal(str)  # format

    def __init__(self, parent=None):
        super().__init__(parent)
        self._products: List[BankProduct] = []
        self._filters = Filters()
        self._current_page = 1
        self._page_size = (
            100  # Увеличиваем размер страницы, чтобы показывать больше данных
        )
        self._sort_field: Optional[str] = None
        self._sort_ascending = True

        self._setup_ui()

    def _setup_ui(self):
        """Настройка UI."""
        # Используем только таблицу, без статистики и пагинации
        # Статистика и пагинация уже есть в UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Таблица - универсальная структура на основе схем нормализации
        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels(
            [
                "Банк",
                "Категория",
                "Название",
                "Описание/Подзаголовок",
                "Ставка %",
                "Сумма/Цена",
                "Срок/Условия",
                "Валюта",
                "Кешбэк",
                "Льготный период",
                "Комиссия",
                "Дата сбора",
            ]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # Устанавливаем растягивание колонок по ширине таблицы
        header = self.table.horizontalHeader()
        # Применяем Stretch ко всем колонкам
        for i in range(self.table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        header.sectionClicked.connect(self._on_header_clicked)
        layout.addWidget(self.table)

    def set_products(self, products: List[BankProduct]) -> None:
        """Устанавливает список продуктов."""
        self._products = products
        self._update_table()

    def set_filters(self, filters: Filters) -> None:
        """Устанавливает фильтры."""
        self._filters = filters
        self._update_table()

    def _update_table(self) -> None:
        """Обновляет таблицу."""
        # Применяем фильтры (здесь должна быть логика фильтрации)
        filtered = self._products

        # Сортировка
        if self._sort_field:
            # Здесь должна быть логика сортировки
            pass

        # Показываем все отфильтрованные продукты без пагинации
        # Заполняем таблицу - все значения должны быть строками для Qt
        self.table.setRowCount(len(filtered))
        for row, product in enumerate(filtered):
            # Банк (всегда строка)
            self.table.setItem(
                row, 0, QTableWidgetItem(str(product.bank) if product.bank else "")
            )

            # Категория (всегда строка)
            category_display = {
                "deposit": "Вклад",
                "credit": "Кредит",
                "debitcard": "Дебетовая карта",
                "creditcard": "Кредитная карта",
            }.get(
                product.category.value,
                str(product.category.value) if product.category else "",
            )
            self.table.setItem(row, 1, QTableWidgetItem(category_display))

            # Название продукта (всегда строка)
            self.table.setItem(
                row, 2, QTableWidgetItem(str(product.product) if product.product else "")
            )

            # Описание/Подзаголовок (пустое, так как в модели BankProduct нет поля description)
            self.table.setItem(row, 3, QTableWidgetItem(""))

            # Ставка % (всегда строка)
            if product.rate_min == product.rate_max:
                rate_text = f"{product.rate_min}%" if product.rate_min > 0 else ""
            else:
                if product.rate_max > 0:
                    rate_text = f"{product.rate_min}% - {product.rate_max}%"
                else:
                    rate_text = f"{product.rate_min}%" if product.rate_min > 0 else ""
            self.table.setItem(row, 4, QTableWidgetItem(rate_text))

            # Сумма/Цена (всегда строка)
            if product.amount_min == product.amount_max:
                if product.amount_min > 0:
                    # Форматируем большие числа
                    if product.amount_min >= 1_000_000_000:
                        amount_text = f"{product.amount_min / 1_000_000_000:.1f} млрд"
                    elif product.amount_min >= 1_000_000:
                        amount_text = f"{product.amount_min / 1_000_000:.1f} млн"
                    elif product.amount_min >= 1_000:
                        amount_text = f"{product.amount_min / 1_000:.1f} тыс"
                    else:
                        amount_text = f"{product.amount_min:,.0f}"
                else:
                    amount_text = ""
            else:
                if product.amount_max > 0:
                    # Форматируем диапазон
                    min_text = (
                        f"{product.amount_min / 1_000_000:.1f} млн"
                        if product.amount_min >= 1_000_000
                        else f"{product.amount_min:,.0f}"
                    )
                    max_text = (
                        f"{product.amount_max / 1_000_000:.1f} млн"
                        if product.amount_max >= 1_000_000
                        else f"{product.amount_max:,.0f}"
                    )
                    amount_text = f"{min_text} - {max_text}"
                else:
                    amount_text = (
                        f"{product.amount_min:,.0f}" if product.amount_min > 0 else ""
                    )
            self.table.setItem(row, 5, QTableWidgetItem(amount_text))

            # Срок/Условия (всегда строка)
            self.table.setItem(
                row, 6, QTableWidgetItem(str(product.term) if product.term else "")
            )

            # Валюта (всегда строка)
            self.table.setItem(
                row,
                7,
                QTableWidgetItem(
                    str(product.currency.value) if product.currency else ""
                ),
            )

            # Кешбэк (всегда строка)
            self.table.setItem(
                row,
                8,
                QTableWidgetItem(str(product.cashback) if product.cashback else ""),
            )

            # Льготный период (всегда строка)
            self.table.setItem(
                row,
                9,
                QTableWidgetItem(
                    str(product.grace_period) if product.grace_period else ""
                ),
            )

            # Комиссия (всегда строка)
            self.table.setItem(
                row,
                10,
                QTableWidgetItem(str(product.commission) if product.commission else ""),
            )

            # Дата сбора (всегда строка)
            date_str = (
                product.collected_at.strftime("%d.%m.%Y %H:%M")
                if product.collected_at
                else ""
            )
            self.table.setItem(row, 11, QTableWidgetItem(date_str))

        # Автоматически изменяем высоту строк по содержимому
        self.table.resizeRowsToContents()

        # Пагинация и статистика обновляются в main_window через UI виджеты

    def _on_header_clicked(self, column: int) -> None:
        """Обработчик клика по заголовку колонки."""
        # Здесь должна быть логика сортировки
        pass
