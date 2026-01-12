import asyncio
import sys

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory
from qasync import QEventLoop

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

    # Принудительно устанавливаем светлую тему
    # Устанавливаем стиль Fusion (кросс-платформенный, поддерживает светлую тему)
    available_styles = QStyleFactory.keys()
    if "Fusion" in available_styles:
        app.setStyle("Fusion")
    elif available_styles:
        app.setStyle(available_styles[0])

    # Устанавливаем светлую палитру принудительно
    palette = QPalette()
    # Фон
    palette.setColor(QPalette.ColorRole.Window, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(0, 0, 0))
    # Кнопки
    palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(0, 0, 0))
    # Базовые цвета
    palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 245))
    palette.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
    # Акцентные цвета
    palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 215))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    # Отключенные элементы (используем правильный синтаксис PyQt6)
    # В PyQt6 ColorGroup - это вложенный enum в QPalette
    disabled_group = QPalette.ColorGroup.Disabled
    palette.setColor(
        disabled_group, QPalette.ColorRole.WindowText, QColor(127, 127, 127)
    )
    palette.setColor(disabled_group, QPalette.ColorRole.Text, QColor(127, 127, 127))
    palette.setColor(
        disabled_group, QPalette.ColorRole.ButtonText, QColor(127, 127, 127)
    )

    app.setPalette(palette)

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
