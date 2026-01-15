import asyncio
import sys

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

from core.theme import apply_theme
from ui.main_window import MainWindow


class WidgetClickLogger(QObject):
    """Глобальный event filter для логирования всех кликов по виджетам."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            widget_info = self._get_widget_info(obj)
            print(f"[CLICK LOG] {widget_info}")
        return super().eventFilter(obj, event)

    def _get_widget_info(self, widget):
        info = []
        if widget:
            info.append(f"Type: {type(widget).__name__}")
            if hasattr(widget, "objectName") and widget.objectName():
                info.append(f"ObjectName: {widget.objectName()}")
            if hasattr(widget, "text") and callable(widget.text):
                text = widget.text()
                if text:
                    info.append(f"Text: {text}")
            if hasattr(widget, "parent") and callable(widget.parent):
                parent = widget.parent()
                if parent and hasattr(parent, "objectName") and parent.objectName():
                    info.append(f"Parent: {parent.objectName()}")

            path = []
            current = widget
            while current:
                name = getattr(current, "objectName", lambda: "")()
                if not name:
                    name = type(current).__name__
                path.insert(0, name)
                current = getattr(current, "parent", lambda: None)()
                if not current or not hasattr(current, "parent"):
                    break
            info.append(f"Path: {' > '.join(path)}")
        return " | ".join(info)


async def main_async(app: QApplication) -> int:
    """Асинхронная инициализация и запуск главного окна."""
    app.setApplicationName("BankMonitor")
    app.setOrganizationName("BankMonitor")
    app.setQuitOnLastWindowClosed(True)

    # Применяем светлую тему по умолчанию
    apply_theme(app, "Светлая")

    # Сохраняем ссылку на app для применения темы
    sys.modules['app_instance'] = app

    # click_logger = WidgetClickLogger()
    # app.installEventFilter(click_logger)
    # print("[DEBUG] Глобальное логирование кликов включено. Кликните на виджет, чтобы увидеть информацию о нем.")

    main_window = MainWindow()
    main_window.show()

    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)

    await app_close_event.wait()
    return 0


def main() -> int:
    app = QApplication(sys.argv)
    return asyncio.run(main_async(app), loop_factory=QEventLoop)


if __name__ == "__main__":
    sys.exit(main())
