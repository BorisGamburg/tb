from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QGraphicsView


class ChartView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)

        self.setBackgroundBrush(
            QBrush(QColor("#202020"))
        )

        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag
        )

        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )

        self.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            False,
        )

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            factor = 1.15
        else:
            factor = 1 / 1.15

        self.scale(factor, factor)

