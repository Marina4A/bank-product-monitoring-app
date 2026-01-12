from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.models import LogEntry


class LogsWidget(QWidget):
    """Виджет для отображения логов."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logs: List[LogEntry] = []
        self._current_filter: Optional[str] = None
        self._search_query: str = ""
        self._is_expanded = False
        self._setup_ui()

    def _setup_ui(self):
        """Настройка UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Кнопка сворачивания/разворачивания
        self.toggle_button = QPushButton("▼ Логи системы (0)")
        self.toggle_button.setCheckable(True)
        self.toggle_button.clicked.connect(self._on_toggle)
        layout.addWidget(self.toggle_button)

        # Контент логов (скрыт по умолчанию)
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)

        # Фильтры и поиск
        filters_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск в логах...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        filters_layout.addWidget(self.search_edit)

        self.all_button = QPushButton("ALL")
        self.all_button.setCheckable(True)
        self.all_button.setChecked(True)
        self.all_button.clicked.connect(lambda: self._set_filter("ALL"))
        filters_layout.addWidget(self.all_button)

        self.info_button = QPushButton("INFO")
        self.info_button.setCheckable(True)
        self.info_button.clicked.connect(lambda: self._set_filter("INFO"))
        filters_layout.addWidget(self.info_button)

        self.warning_button = QPushButton("WARNING")
        self.warning_button.setCheckable(True)
        self.warning_button.clicked.connect(lambda: self._set_filter("WARNING"))
        filters_layout.addWidget(self.warning_button)

        self.error_button = QPushButton("ERROR")
        self.error_button.setCheckable(True)
        self.error_button.clicked.connect(lambda: self._set_filter("ERROR"))
        filters_layout.addWidget(self.error_button)

        content_layout.addLayout(filters_layout)

        # Список логов
        self.logs_list = QListWidget()
        self.logs_list.setMaximumHeight(200)
        content_layout.addWidget(self.logs_list)

        layout.addWidget(self.content_widget)
        self.content_widget.setVisible(False)

    def add_log(self, log: LogEntry) -> None:
        """Добавляет запись в лог."""
        self._logs.insert(0, log)
        self._update_logs()
        self._update_toggle_button()

    def set_logs(self, logs: List[LogEntry]) -> None:
        """Устанавливает список логов."""
        self._logs = logs
        self._update_logs()
        self._update_toggle_button()

    def _on_toggle(self) -> None:
        """Обработчик сворачивания/разворачивания."""
        # Проверяем, что кнопка существует и не была удалена
        if not hasattr(self, 'toggle_button') or self.toggle_button is None:
            return
        try:
            self._is_expanded = self.toggle_button.isChecked()
            self.content_widget.setVisible(self._is_expanded)
            self.toggle_button.setText("▲" if self._is_expanded else "▼")
        except RuntimeError:
            # Кнопка была удалена, устанавливаем в None
            self.toggle_button = None
            return

    def _on_search_changed(self, text: str) -> None:
        """Обработчик изменения поискового запроса."""
        self._search_query = text
        self._update_logs()

    def _set_filter(self, level: str) -> None:
        """Устанавливает фильтр по уровню."""
        self._current_filter = None if level == "ALL" else level

        # Обновляем состояние кнопок
        self.all_button.setChecked(level == "ALL")
        self.info_button.setChecked(level == "INFO")
        self.warning_button.setChecked(level == "WARNING")
        self.error_button.setChecked(level == "ERROR")

        self._update_logs()

    def _update_logs(self) -> None:
        """Обновляет отображаемые логи."""
        self.logs_list.clear()

        # Фильтруем логи
        filtered = self._logs

        if self._current_filter:
            filtered = [log for log in filtered if log.level == self._current_filter]

        if self._search_query:
            query = self._search_query.lower()
            filtered = [log for log in filtered if query in log.message.lower()]

        # Добавляем в список
        for log in filtered[:100]:  # Ограничиваем до 100 записей
            item_text = f"[{log.timestamp.strftime('%H:%M:%S')}] {log.level}: {log.message}"
            item = QListWidgetItem(item_text)

            # Цвет в зависимости от уровня
            if log.level == "ERROR":
                item.setForeground(Qt.GlobalColor.red)
            elif log.level == "WARNING":
                item.setForeground(Qt.GlobalColor.yellow)
            else:
                item.setForeground(Qt.GlobalColor.blue)

            self.logs_list.addItem(item)

    def _update_toggle_button(self) -> None:
        """Обновляет текст кнопки переключения."""
        # Проверяем, что кнопка существует и не была удалена
        if not hasattr(self, 'toggle_button') or self.toggle_button is None:
            return
        try:
            # Пытаемся обратиться к кнопке - если она удалена, будет RuntimeError
            count = len(self._logs)
            self.toggle_button.setText(f"{'▲' if self._is_expanded else '▼'} Логи системы ({count})")
        except RuntimeError:
            # Кнопка была удалена, устанавливаем в None
            self.toggle_button = None
            return
