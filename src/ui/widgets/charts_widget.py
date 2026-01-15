from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.models import BankProduct


class ChartsWidget(QWidget):
    """Виджет для отображения графиков."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._products: List[BankProduct] = []
        self._current_chart_type = "line"
        self._setup_ui()

    def _setup_ui(self):
        """Настройка UI."""
        layout = QVBoxLayout(self)

        # Кнопки выбора типа графика
        chart_type_layout = QHBoxLayout()
        self.line_button = QPushButton("Динамика ставок")
        self.line_button.setCheckable(True)
        self.line_button.setChecked(True)
        self.line_button.clicked.connect(lambda: self._set_chart_type("line"))

        self.bar_button = QPushButton("Сравнение банков")
        self.bar_button.setCheckable(True)
        self.bar_button.clicked.connect(lambda: self._set_chart_type("bar"))

        self.pie_button = QPushButton("Распределение")
        self.pie_button.setCheckable(True)
        self.pie_button.clicked.connect(lambda: self._set_chart_type("pie"))

        self.scatter_button = QPushButton("Корреляции")
        self.scatter_button.setCheckable(True)
        self.scatter_button.clicked.connect(lambda: self._set_chart_type("scatter"))

        chart_type_layout.addWidget(self.line_button)
        chart_type_layout.addWidget(self.bar_button)
        chart_type_layout.addWidget(self.pie_button)
        chart_type_layout.addWidget(self.scatter_button)
        chart_type_layout.addStretch()

        self.download_button = QPushButton("📥")
        chart_type_layout.addWidget(self.download_button)
        layout.addLayout(chart_type_layout)

        # Placeholder для графиков
        self.chart_placeholder = QLabel("Графики будут здесь\nTODO: Интегрировать matplotlib или другой графический движок")
        self.chart_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chart_placeholder.setMinimumHeight(400)
        layout.addWidget(self.chart_placeholder)

    def set_products(self, products: List[BankProduct]) -> None:
        """Устанавливает список продуктов."""
        self._products = products
        self._update_charts()

    def _set_chart_type(self, chart_type: str) -> None:
        """Устанавливает тип графика."""
        self._current_chart_type = chart_type

        # Обновляем состояние кнопок
        self.line_button.setChecked(chart_type == "line")
        self.bar_button.setChecked(chart_type == "bar")
        self.pie_button.setChecked(chart_type == "pie")
        self.scatter_button.setChecked(chart_type == "scatter")

        self._update_charts()

    def _update_charts(self) -> None:
        """Обновляет графики."""
        # TODO: Реализовать отображение графиков
        # Здесь должна быть логика создания и обновления графиков
        # Можно использовать matplotlib, pyqtgraph или другие библиотеки
        pass
    
    def update_theme_colors(self, theme_colors: dict):
        """
        Обновляет цвета графиков в соответствии с темой.
        
        Args:
            theme_colors: Словарь с цветами темы (background, text, grid, axes)
        """
        # TODO: Применить цвета темы, когда графики будут реализованы
        pass
