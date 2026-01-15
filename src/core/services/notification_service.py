"""Сервис для управления уведомлениями в приложении."""

from typing import Optional
from PyQt6.QtWidgets import QMessageBox, QSystemTrayIcon, QApplication
from PyQt6.QtCore import QObject, pyqtSignal


class NotificationService(QObject):
    """Сервис для отображения уведомлений пользователю."""

    # Сигналы для различных типов уведомлений
    notification_shown = pyqtSignal(str, str)  # type, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._notify_new_data = True
        self._notify_errors = True

    def set_settings(self, settings: dict):
        """
        Устанавливает настройки уведомлений.

        Args:
            settings: Словарь с настройками:
                - notify_on_new_data: bool - уведомлять при обновлении данных
                - notify_on_errors: bool - уведомлять при ошибках
        """
        self._notify_new_data = settings.get("notify_on_new_data", True)
        self._notify_errors = settings.get("notify_on_errors", True)

    def notify_new_data(self, message: str, details: Optional[str] = None):
        """
        Показывает уведомление об обновлении данных.

        Args:
            message: Основное сообщение
            details: Дополнительная информация (опционально)
        """
        if not self._notify_new_data:
            return

        full_message = message
        if details:
            full_message += f"\n{details}"

        QMessageBox.information(
            None,
            "Обновление данных",
            full_message
        )
        self.notification_shown.emit("new_data", full_message)

    def notify_error(self, message: str, details: Optional[str] = None):
        """
        Показывает уведомление об ошибке.

        Args:
            message: Основное сообщение об ошибке
            details: Дополнительная информация (опционально)
        """
        if not self._notify_errors:
            return

        full_message = message
        if details:
            full_message += f"\n{details}"

        QMessageBox.critical(
            None,
            "Ошибка",
            full_message
        )
        self.notification_shown.emit("error", full_message)

    def notify_info(self, message: str, details: Optional[str] = None):
        """
        Показывает информационное уведомление.

        Args:
            message: Основное сообщение
            details: Дополнительная информация (опционально)
        """
        # Информационные уведомления всегда показываются
        pass

        full_message = message
        if details:
            full_message += f"\n{details}"

        QMessageBox.information(
            None,
            "Информация",
            full_message
        )
        self.notification_shown.emit("info", full_message)
