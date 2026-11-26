from datetime import datetime

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from candle_item import CandleItem
from level_item import LevelItem


def get_price_range(candles, levels):
    prices = []

    for timestamp, open_price, high, low, close in candles:
        prices.extend(
            [
                open_price,
                high,
                low,
                close,
            ]
        )

    for price, qty in levels:
        prices.append(price)

    return min(prices), max(prices)


def create_candles(
    scene,
    candles,
    center_price,
    y_scale,
    center_y,
    candle_spacing,
    left_margin=130,
    parent=None,
):
    for i, (
        timestamp,
        open_price,
        high,
        low,
        close,
    ) in enumerate(candles):
        x = i * candle_spacing + left_margin

        candle = CandleItem(
            x=x,
            open_price=open_price,
            high=high,
            low=low,
            close=close,
            center_price=center_price,
            y_scale=y_scale,
            center_y=center_y,
        )

        if parent is None:
            scene.addItem(candle)
        else:
            candle.setParentItem(parent)


def create_price_to_y(
    center_price,
    y_scale,
    center_y,
):
    def price_to_y(price):
        return (
            center_y
            - (price - center_price)
            * y_scale
        )

    return price_to_y


def create_time_axis(
    scene,
    candles,
    candle_count,
    candle_spacing,
    time_axis_y,
    left_margin=130,
):
    time_step = max(
        1,
        candle_count // 5,
    )

    for i in range(
        0,
        candle_count,
        time_step,
    ):
        timestamp = candles[i][0]

        x = (
            i * candle_spacing
            + left_margin
        )

        time_label = QGraphicsTextItem(
            datetime.fromtimestamp(
                timestamp / 1000
            ).strftime("%H:%M")
        )

        time_label.setDefaultTextColor(
            QColor("#ffffff")
        )

        time_label.setPos(
            x - 20,
            time_axis_y,
        )

        scene.addItem(time_label)


def create_price_axis(
    scene,
    price_to_y,
    price_min,
    price_max,
    price_axis_x,
):
    min_label_spacing = 30
    y_scale = abs(price_to_y(price_min) - price_to_y(price_max)) / (
        price_max - price_min
    )

    price_step = 0.0002

    if y_scale > 0:
        min_price_step = min_label_spacing / y_scale

        while price_step < min_price_step:
            price_step *= 2

    price_start = (
        int(price_min / price_step)
        * price_step
    )

    price_end = (
        int(price_max / price_step + 1)
        * price_step
    )

    price = price_start

    while price <= price_end:
        y = price_to_y(price)

        # При увеличении не рисуем цены за пределами графика
        if not (
            price_to_y(price_max) - 15
            <= y
            <= price_to_y(price_min) + 15
        ):
            price += price_step
            continue

        price_label = QGraphicsTextItem(
            f"{price:.6f}"
        )

        price_label.setDefaultTextColor(
            QColor("#ffffff")
        )

        price_label.setPos(
            price_axis_x,
            y - 10,
        )

        scene.addItem(price_label)

        price += price_step
def create_levels(
    scene,
    levels,
    price_to_y,
    chart_width,
    level_label_width,
):
    label_items = []

    for price, qty in levels:
        y = price_to_y(price)

        level = LevelItem(
            price=price,
            qty=qty,
            y=y,
            x=level_label_width,
            width=chart_width - level_label_width,
        )

        scene.addItem(level)

        label = QGraphicsTextItem(
            f"{price:.6f}  ×{qty:g}"
        )

        label.setDefaultTextColor(
            QColor("#ffffff")
        )

        label_items.append((y, label))

    label_items.sort(key=lambda item: item[0])

    min_label_spacing = 18
    previous_y = None

    for y, label in label_items:
        label_y = y - 10

        if previous_y is not None:
            label_y = max(
                label_y,
                previous_y + min_label_spacing,
            )

        label.setPos(0, label_y)
        scene.addItem(label)

        previous_y = label_y


def get_chart_geometry(
    candles,
    levels,
    candle_count,
    candle_spacing,
    chart_height,
    price_axis_width,
    left_margin=130,
    right_margin=60,
):
    price_min, price_max = get_price_range(
        candles,
        levels,
    )

    center_price = (
        price_min + price_max
    ) / 2

    y_scale = (
        chart_height
        / (price_max - price_min)
    )

    candles_width = (
        candle_count * candle_spacing
        + left_margin
    )

    chart_width = candles_width + right_margin

    scene_width = (
        chart_width
        + price_axis_width
    )

    return (
        price_min,
        price_max,
        chart_width,
        scene_width,
        center_price,
        y_scale,
    )


def get_max_zoom(candles, levels, chart_height):
    # Наибольшее увеличение, при котором все уровни ещё видны
    if not levels:
        return 1.0

    price_min, price_max = get_price_range(candles, levels)
    prices = [price for price, qty in levels]
    levels_range = max(prices) - min(prices)

    if levels_range <= 0:
        return 1.0

    return max(
        1.0,
        (chart_height - 20)
        / chart_height
        * (price_max - price_min)
        / levels_range,
    )


def create_chart(
    candles,
    levels,
    candle_count,
    candle_spacing,
    chart_height,
    price_axis_width,
    center_y,
    time_axis_y=None,  # Делаем опциональным
    zoom=1.0,
):
    scene = QGraphicsScene()

    level_label_width = 120
    left_margin = level_label_width + 10

    # Если time_axis_y не передан явно, ставим его под нижний край графика
    if time_axis_y is None:
        time_axis_y = center_y + (chart_height / 2) + 20

    (
        price_min,
        price_max,
        chart_width,
        scene_width,
        center_price,
        y_scale,
    ) = get_chart_geometry(
        candles,
        levels,
        candle_count,
        candle_spacing,
        chart_height,
        price_axis_width,
        left_margin=left_margin,
        right_margin=60,
    )

    # Увеличение только по цене: растягиваем вокруг середины уровней
    if zoom > 1 and levels:
        prices = [price for price, qty in levels]
        center_price = (min(prices) + max(prices)) / 2
        y_scale *= zoom

        half_range = chart_height / 2 / y_scale
        price_min = center_price - half_range
        price_max = center_price + half_range

    price_to_y = create_price_to_y(
        center_price,
        y_scale,
        center_y,
    )

    # Область, за пределами которой свечи обрезаются
    clip = QGraphicsRectItem(
        0,
        center_y - chart_height / 2 - 1,
        chart_width,
        chart_height + 2,
    )
    clip.setPen(QPen(Qt.PenStyle.NoPen))
    clip.setFlag(
        QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape
    )
    scene.addItem(clip)

    create_candles(
        scene,
        candles,
        center_price,
        y_scale,
        center_y,
        candle_spacing,
        left_margin=left_margin,
        parent=clip,
    )

    create_time_axis(
        scene,
        candles,
        candle_count,
        candle_spacing,
        time_axis_y,
        left_margin=left_margin,
    )

    create_price_axis(
        scene,
        price_to_y,
        price_min,
        price_max,
        chart_width + 15,
    )


    create_levels(
        scene,
        levels,
        price_to_y,
        chart_width,
        level_label_width,
    )

    scene.setSceneRect(
        QRectF(
            0,
            0,
            scene_width,
            time_axis_y + 40,  # Ограничиваем сцену с учетом высоты шрифта
        )
    )

    return scene