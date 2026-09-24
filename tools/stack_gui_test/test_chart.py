import sys
import yaml

from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chart import create_chart
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

    scene = create_chart(
        candles,
        levels,
        candle_count,
        candle_spacing,
        chart_height,
        price_axis_width,
        center_y,
        time_axis_y,
    )

    view = ChartView(scene)

    window = QWidget()

    button = QPushButton("Merge")
    button.clicked.connect(
        lambda: confirm_merge(
            scene,
            window,
            config_path,
            config,
        )
    )

    layout = QVBoxLayout(window)
    layout.addWidget(button)
    layout.addWidget(view)

    window.resize(1300, 750)
    window.show()

    sys.exit(app.exec())

    
if __name__ == "__main__":
    main()