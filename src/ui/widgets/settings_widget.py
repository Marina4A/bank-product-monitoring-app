from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SettingsWidget(QWidget):
    """Виджет настроек."""

    # Сигналы
    settings_saved = pyqtSignal(dict)  # settings dict
    settings_reset = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._load_default_settings()

    def _setup_ui(self):
        """Настройка UI."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        # Настройки парсинга
        parsing_group = QGroupBox("Настройки парсинга")
        parsing_layout = QVBoxLayout()

        update_interval_layout = QHBoxLayout()
        update_interval_layout.addWidget(QLabel("Интервал обновления (минуты):"))
        self.update_interval_spin = QSpinBox()
        self.update_interval_spin.setMinimum(360)  # Минимум 6 часов
        self.update_interval_spin.setMaximum(1440)
        self.update_interval_spin.setValue(360)  # По умолчанию 6 часов
        update_interval_layout.addWidget(self.update_interval_spin)
        update_interval_layout.addStretch()
        parsing_layout.addLayout(update_interval_layout)

        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(QLabel("Таймаут запроса (секунды):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setMinimum(1)
        self.timeout_spin.setMaximum(300)
        self.timeout_spin.setValue(30)
        timeout_layout.addWidget(self.timeout_spin)
        timeout_layout.addStretch()
        parsing_layout.addLayout(timeout_layout)

        retries_layout = QHBoxLayout()
        retries_layout.addWidget(QLabel("Количество повторов:"))
        self.retries_spin = QSpinBox()
        self.retries_spin.setMinimum(1)
        self.retries_spin.setMaximum(10)
        self.retries_spin.setValue(3)
        retries_layout.addWidget(self.retries_spin)
        retries_layout.addStretch()
        parsing_layout.addLayout(retries_layout)

        parsing_group.setLayout(parsing_layout)
        layout.addWidget(parsing_group)

        # Уведомления
        notifications_group = QGroupBox("Уведомления")
        notifications_layout = QVBoxLayout()

        self.enable_notifications_check = QCheckBox("Включить уведомления")
        self.enable_notifications_check.setChecked(True)
        notifications_layout.addWidget(self.enable_notifications_check)

        self.notify_new_data_check = QCheckBox("Уведомлять при обновлении данных")
        self.notify_new_data_check.setChecked(True)
        notifications_layout.addWidget(self.notify_new_data_check)

        self.notify_errors_check = QCheckBox("Уведомлять при ошибках парсинга")
        self.notify_errors_check.setChecked(True)
        notifications_layout.addWidget(self.notify_errors_check)

        notifications_group.setLayout(notifications_layout)
        layout.addWidget(notifications_group)

        # Фильтры по умолчанию
        filters_group = QGroupBox("Фильтры по умолчанию")
        filters_layout = QVBoxLayout()

        default_bank_layout = QHBoxLayout()
        default_bank_layout.addWidget(QLabel("Банк:"))
        self.default_bank_combo = QComboBox()
        self.default_bank_combo.addItems(
            ["Все банки", "Sberbank", "TBank", "VTB", "Alfa-Bank"]
        )
        default_bank_layout.addWidget(self.default_bank_combo)
        default_bank_layout.addStretch()
        filters_layout.addLayout(default_bank_layout)

        default_category_layout = QHBoxLayout()
        default_category_layout.addWidget(QLabel("Категория:"))
        self.default_category_combo = QComboBox()
        self.default_category_combo.addItems(
            ["Все", "Вклады", "Кредиты", "Дебетовые карты", "Кредитные карты"]
        )
        default_category_layout.addWidget(self.default_category_combo)
        default_category_layout.addStretch()
        filters_layout.addLayout(default_category_layout)

        default_currency_layout = QHBoxLayout()
        default_currency_layout.addWidget(QLabel("Валюта:"))
        self.default_currency_combo = QComboBox()
        self.default_currency_combo.addItems(["Все валюты", "RUB", "USD", "EUR", "CNY"])
        default_currency_layout.addWidget(self.default_currency_combo)
        default_currency_layout.addStretch()
        filters_layout.addLayout(default_currency_layout)

        filters_group.setLayout(filters_layout)
        layout.addWidget(filters_group)

        # Отображение
        display_group = QGroupBox("Отображение")
        display_layout = QVBoxLayout()

        page_size_layout = QHBoxLayout()
        page_size_layout.addWidget(QLabel("Строк на странице:"))
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["10", "50", "100"])
        self.page_size_combo.setCurrentText("10")
        page_size_layout.addWidget(self.page_size_combo)
        page_size_layout.addStretch()
        display_layout.addLayout(page_size_layout)

        self.auto_refresh_check = QCheckBox("Авто-обновление")
        self.auto_refresh_check.setChecked(True)
        display_layout.addWidget(self.auto_refresh_check)

        auto_refresh_interval_layout = QHBoxLayout()
        auto_refresh_interval_layout.addWidget(QLabel("Интервал обновления (секунды):"))
        self.auto_refresh_interval_spin = QSpinBox()
        self.auto_refresh_interval_spin.setMinimum(10)
        self.auto_refresh_interval_spin.setMaximum(3600)
        self.auto_refresh_interval_spin.setValue(300)
        auto_refresh_interval_layout.addWidget(self.auto_refresh_interval_spin)
        auto_refresh_interval_layout.addStretch()
        display_layout.addLayout(auto_refresh_interval_layout)

        display_group.setLayout(display_layout)
        layout.addWidget(display_group)

        # Кнопки
        buttons_layout = QHBoxLayout()
        self.save_button = QPushButton("Сохранить настройки")
        self.save_button.clicked.connect(self._on_save)
        self.reset_button = QPushButton("Сбросить")
        self.reset_button.clicked.connect(self._on_reset)
        buttons_layout.addWidget(self.save_button)
        buttons_layout.addWidget(self.reset_button)
        layout.addLayout(buttons_layout)

        layout.addStretch()
        scroll.setWidget(scroll_widget)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll)

    def _load_default_settings(self) -> None:
        """Загружает настройки по умолчанию."""
        # Здесь можно загрузить настройки из файла или базы данных
        pass

    def get_settings(self) -> dict:
        """Возвращает текущие настройки."""
        return {
            "update_interval": self.update_interval_spin.value(),
            "timeout": self.timeout_spin.value(),
            "retries": self.retries_spin.value(),
            "enable_notifications": self.enable_notifications_check.isChecked(),
            "notify_on_new_data": self.notify_new_data_check.isChecked(),
            "notify_on_errors": self.notify_errors_check.isChecked(),
            "default_bank": self.default_bank_combo.currentText(),
            "default_category": self.default_category_combo.currentText(),
            "default_currency": self.default_currency_combo.currentText(),
            "page_size": int(self.page_size_combo.currentText()),
            "auto_refresh": self.auto_refresh_check.isChecked(),
            "auto_refresh_interval": self.auto_refresh_interval_spin.value(),
        }

    def set_settings(self, settings: dict) -> None:
        """Устанавливает настройки."""
        self.update_interval_spin.setValue(settings.get("update_interval", 60))
        self.timeout_spin.setValue(settings.get("timeout", 30))
        self.retries_spin.setValue(settings.get("retries", 3))
        self.enable_notifications_check.setChecked(
            settings.get("enable_notifications", True)
        )
        self.notify_new_data_check.setChecked(settings.get("notify_on_new_data", True))
        self.notify_errors_check.setChecked(settings.get("notify_on_errors", True))
        # ... и т.д.

    def _on_save(self) -> None:
        """Обработчик сохранения настроек."""
        settings = self.get_settings()
        self.settings_saved.emit(settings)
        # TODO: Показать уведомление об успешном сохранении

    def _on_reset(self) -> None:
        """Обработчик сброса настроек."""
        self._load_default_settings()
        self.settings_reset.emit()
