from datetime import datetime

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
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

        scene.addItem(candle)


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
    price_step = 0.0002

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

        label.setPos(
            0,
            y - 10,
        )

        scene.addItem(label)


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


def create_chart(
    candles,
    levels,
    candle_count,
    candle_spacing,
    chart_height,
    price_axis_width,
    center_y,
    time_axis_y=None,  # Делаем опциональным
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

    price_to_y = create_price_to_y(
        center_price,
        y_scale,
        center_y,
    )

    create_candles(
        scene,
        candles,
        center_price,
        y_scale,
        center_y,
        candle_spacing,
        left_margin=left_margin,
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