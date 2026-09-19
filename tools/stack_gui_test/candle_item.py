from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

class CandleItem(QGraphicsItem):
    def __init__(
        self,
        x,
        open_price,
        high,
        low,
        close,
        center_price,
        y_scale,
        center_y,
    ):
        super().__init__()

        self.x = x
        self.open_price = open_price
        self.high = high
        self.low = low
        self.close = close
        self.center_price = center_price
        self.y_scale = y_scale
        self.center_y = center_y

        self.width = 5

    def price_to_y(self, price):
        return (
            self.center_y
            - (price - self.center_price) * self.y_scale
        )

    def boundingRect(self):
        y_high = self.price_to_y(self.high)
        y_low = self.price_to_y(self.low)

        return QRectF(
            self.x - self.width - 1,
            y_high - 1,
            self.width * 2 + 2,
            y_low - y_high + 2,
        )

    def paint(self, painter, option, widget=None):
        y_open = self.price_to_y(self.open_price)
        y_high = self.price_to_y(self.high)
        y_low = self.price_to_y(self.low)
        y_close = self.price_to_y(self.close)

        if self.close >= self.open_price:
            color = QColor("#26a69a")
        else:
            color = QColor("#ef5350")

        # Wick
        painter.setPen(QPen(color, 1))
        painter.drawLine(
            self.x,
            y_high,
            self.x,
            y_low,
        )

        # Body
        top = min(y_open, y_close)
        bottom = max(y_open, y_close)

        if bottom - top < 1:
            bottom = top + 1

        painter.setPen(QPen(color, 1))
        painter.setBrush(QBrush(color))

        painter.drawRect(
            QRectF(
                self.x - self.width,
                top,
                self.width * 2,
                bottom - top,
            )
        )

