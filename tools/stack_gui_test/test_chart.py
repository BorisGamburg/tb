import sys
import yaml

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chart import create_chart, get_max_zoom
from chart_view import ChartView
from market_data import get_candles
from PySide6.QtWidgets import QGraphicsView



def load_config(config_path):
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_levels(config):
    return [
        (
            entry["price"],
            entry["qty"],
        )
        for entry in config["stack"]["entries"]
    ]


def confirm_merge(scene, window, config_path, config):
    selected_items = scene.selectedItems()
    
    if not selected_items:
        return

    selected_levels = [
        (item.price, item.qty)
        for item in selected_items
    ]

    message = (
        f"Вы действительно хотите объединить "
        f"эти {len(selected_levels)} уровня?"
    )

    result = QMessageBox.question(
        window,
        "Объединение уровней",
        message,
        QMessageBox.StandardButton.Ok
        | QMessageBox.StandardButton.Cancel,
    )

    if result == QMessageBox.StandardButton.Ok:
        average_price, total_qty = merge_levels(selected_levels)

        # Множество цен выделенных уровней для быстрого поиска и удаления
        prices_to_remove = {price for price, qty in selected_levels}

        # Оставляем только те уровни, которые НЕ были выделены
        new_entries = [
            entry for entry in config["stack"]["entries"]
            if entry["price"] not in prices_to_remove
        ]

        # Добавляем объединенный уровень
        new_entries.append({
            "price": average_price,
            "qty": total_qty
        })

        # Сортируем уровни по убыванию цены (опционально, для порядка в конфиге)
        new_entries.sort(key=lambda x: x["price"], reverse=True)

        # Обновляем структуру и сохраняем файл
        config["stack"]["entries"] = new_entries
        save_config(config_path, config)

        print(f"Обновлено! Объединенный уровень: {average_price}, qty: {total_qty}")
        print(f"Конфиг {config_path} успешно сохранен.")

def merge_levels(levels):
    total_qty = sum(
        qty
        for price, qty in levels
    )

    average_price = (
        sum(
            price * qty
            for price, qty in levels
        )
        / total_qty
    )

    return average_price, total_qty


def set_chart_params():
    candle_count = 100
    candle_spacing = 12
    price_axis_width = 80

    center_y = 300
    chart_height = 500
    time_axis_y = center_y + (chart_height / 2) + 20  # Рассчитываем положение снизу

    return (
        candle_count,
        candle_spacing,
        price_axis_width,
        center_y,
        chart_height,
        time_axis_y,
    )

def get_configdata():
    config = load_config(sys.argv[1])

    symbol = config["symbol"]
    levels = get_levels(config)

    return symbol, levels

def save_config(config_path, config):
    with open(config_path, "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)



def main():
    app = QApplication(sys.argv)

    config_path = sys.argv[1]
    config = load_config(config_path)

    symbol = config["symbol"]
    levels = get_levels(config)

    (
        candle_count,
        candle_spacing,
        price_axis_width,
        center_y,
        chart_height,
        time_axis_y,
    ) = set_chart_params()

    candles = get_candles(
        symbol=symbol,
        interval="60",
        limit=candle_count,
    )

    def build_scene(levels, zoom):
        return create_chart(
            candles,
            levels,
            candle_count,
            candle_spacing,
            chart_height,
            price_axis_width,
            center_y,
            time_axis_y,
            zoom,
        )

    first_scene = build_scene(levels, 1.0)
    view = ChartView(first_scene)
    first_scene.setParent(view)
    zoom = 1.0

    def change_zoom(factor):
        nonlocal zoom

        levels = get_levels(config)
        max_zoom = get_max_zoom(candles, levels, chart_height)
        new_zoom = min(max(zoom * factor, 1.0), max_zoom)

        if abs(new_zoom - zoom) < 1e-9:
            return

        zoom = new_zoom
        old_scene = view.scene()

        # Сохраняем выделение уровней при перерисовке
        selected_prices = {
            item.price for item in old_scene.selectedItems()
        }

        scene = build_scene(levels, zoom)

        for item in scene.items():
            if getattr(item, "price", None) in selected_prices:
                item.setSelected(True)

        scene.setParent(view)
        view.setScene(scene)
        old_scene.deleteLater()

    window = QWidget()
    window.setWindowTitle(f"Stack Grid — {symbol}")

    button = QPushButton("Merge")
    button.clicked.connect(
        lambda: confirm_merge(
            view.scene(),
            window,
            config_path,
            config,
        )
    )

    layout = QVBoxLayout(window)
    layout.addWidget(button)

    zoom_layout = QHBoxLayout()

    for text, factor in (("Zoom In", 1.5), ("Zoom Out", 1 / 1.5)):
        zoom_button = QPushButton(text)
        zoom_button.clicked.connect(
            lambda checked=False, f=factor: change_zoom(f)
        )
        zoom_layout.addWidget(zoom_button)

    layout.addLayout(zoom_layout)
    layout.addWidget(view)

    window.resize(1300, 750)
    window.show()

    sys.exit(app.exec())

    
if __name__ == "__main__":
    main()