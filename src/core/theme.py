"""Модуль для управления темой приложения."""

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory


def apply_theme(app: QApplication, theme: str):
    """
    Применяет тему к приложению.
    
    Args:
        app: Экземпляр QApplication
        theme: "Светлая" или "Темная"
    """
    # Устанавливаем стиль Fusion (кросс-платформенный)
    available_styles = QStyleFactory.keys()
    if "Fusion" in available_styles:
        app.setStyle("Fusion")
    elif available_styles:
        app.setStyle(available_styles[0])
    
    palette = QPalette()
    
    if theme == "Темная":
        # Темная тема
        # Фон
        palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        # Кнопки
        palette.setColor(QPalette.ColorRole.Button, QColor(73, 73, 73))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        # Базовые цвета
        palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
        # Акцентные цвета
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        # Дополнительные роли для полной поддержки темной темы
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.LinkVisited, QColor(130, 130, 218))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(35, 35, 35))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(127, 127, 127))
        # Отключенные элементы
        disabled_group = QPalette.ColorGroup.Disabled
        palette.setColor(disabled_group, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
        palette.setColor(disabled_group, QPalette.ColorRole.Text, QColor(127, 127, 127))
        palette.setColor(disabled_group, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
        palette.setColor(disabled_group, QPalette.ColorRole.Base, QColor(53, 53, 53))
    else:
        # Светлая тема (по умолчанию)
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
        # Дополнительные роли
        palette.setColor(QPalette.ColorRole.Link, QColor(0, 120, 215))
        palette.setColor(QPalette.ColorRole.LinkVisited, QColor(120, 0, 215))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(127, 127, 127))
        # Отключенные элементы
        disabled_group = QPalette.ColorGroup.Disabled
        palette.setColor(disabled_group, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
        palette.setColor(disabled_group, QPalette.ColorRole.Text, QColor(127, 127, 127))
        palette.setColor(disabled_group, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
        palette.setColor(disabled_group, QPalette.ColorRole.Base, QColor(240, 240, 240))
    
    app.setPalette(palette)
    
    # Уведомляем все виджеты об изменении темы
    # Обновляем все виджеты приложения
    style = app.style()
    for widget in app.allWidgets():
        if widget:
            try:
                style.unpolish(widget)
                style.polish(widget)
                widget.update()
            except Exception:
                # Игнорируем ошибки для виджетов, которые не поддерживают unpolish/polish
                pass


def get_theme_colors(theme: str) -> dict:
    """
    Возвращает цвета для графиков в зависимости от темы.
    
    Args:
        theme: "Светлая" или "Темная"
        
    Returns:
        Словарь с цветами для графиков
    """
    if theme == "Темная":
        return {
            "background": "#232323",  # Темный фон
            "text": "#FFFFFF",  # Белый текст
            "grid": "#3A3A3A",  # Серая сетка
            "axes": "#CCCCCC",  # Светло-серая ось
        }
    else:
        return {
            "background": "#FFFFFF",  # Белый фон
            "text": "#000000",  # Черный текст
            "grid": "#E0E0E0",  # Светло-серая сетка
            "axes": "#000000",  # Черная ось
        }
