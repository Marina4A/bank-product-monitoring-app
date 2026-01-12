from typing import Optional

from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from core.services.currency_rates_service import CurrencyRatesService
from ui.widgets.currency_history_widget import CurrencyHistoryWidget
from ui.widgets.currency_widget import RatesWidget


class CurrencyTabWidget(QWidget):
    """Вкладка с виджетами валют."""

    def __init__(
        self,
        currency_rates_service: Optional[CurrencyRatesService] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._currency_rates_service = currency_rates_service
        self._setup_ui()

    def _setup_ui(self):
        """Настройка UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Создаем TabWidget для переключения между виджетами валют
        self.tab_widget = QTabWidget()

        # Виджет текущих курсов с сервисом БД
        self.rates_widget = RatesWidget(
            currency_rates_service=self._currency_rates_service
        )
        self.tab_widget.addTab(self.rates_widget, "Курсы валют")

        # Виджет истории валют
        self.history_widget = CurrencyHistoryWidget()
        self.tab_widget.addTab(self.history_widget, "История валют")

        layout.addWidget(self.tab_widget)
