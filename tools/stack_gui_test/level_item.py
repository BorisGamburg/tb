from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem


class LevelItem(QGraphicsRectItem):
    def __init__(self, price, qty, y, x, width):
        super().__init__(
            0,
            -1,
            width,
            2,
        )

        self.price = price
        self.qty = qty

        self.setPos(x, y)

        self.setPen(
            QPen(QColor("#ff9800"), 0.1)
        )
        self.setBrush(
            QBrush(QColor("#ff9800"))
        )

        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )

        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        self.setPen(
            QPen(QColor("#00aaff"), 3)
        )
        self.setBrush(
            QBrush(QColor("#00aaff"))
        )

        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.isSelected():
            color = QColor("#00ff00")
            width = 3
        else:
            color = QColor("#ff9800")
            width = 1

        self.setPen(QPen(color, width))
        self.setBrush(QBrush(color))

        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if (
            change
            == QGraphicsItem.GraphicsItemChange.ItemSelectedChange
        ):
            if value:
                color = QColor("#00ff00")
                width = 3
            else:
                color = QColor("#ff9800")
                width = 1

            self.setPen(QPen(color, width))
            self.setBrush(QBrush(color))

        return super().itemChange(change, value)


