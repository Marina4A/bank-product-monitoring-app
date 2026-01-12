from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout


class StatCard(QFrame):
    """Карточка для отображения статистики."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        layout = QVBoxLayout(self)

        self.value_label = QLabel("0")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        font = self.value_label.font()
        font.setPointSize(24)
        font.setBold(True)
        self.value_label.setFont(font)

        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self.value_label)
        layout.addWidget(self.label)

    def set_value(self, value: str) -> None:
        """Устанавливает значение."""
        self.value_label.setText(value)

    def set_label(self, label: str) -> None:
        """Устанавливает подпись."""
        self.label.setText(label)
