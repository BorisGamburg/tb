from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from pathlib import Path
from datetime import datetime



def get_inverse_side(current_side: str) -> str:
    """
    Возвращает противоположную сторону сделки ('Buy' -> 'Sell', 'Sell' -> 'Buy').
    Эта утилита доступна всем модулям, так как находится на верхнем уровне.
    """
    if current_side == "Buy":
        return "Sell"
    elif current_side == "Sell":
        return "Buy"
    # Доменная логика: если сторона не определена, это ошибка.
    raise ValueError(f"Неизвестная сторона: {current_side}")

def remove_state_file(
    state_dir: str, 
    config_tag: str, 
    logger: Any
) -> None:
    state_dir_var = Path(state_dir)
    state_file = state_dir_var / f"{config_tag}.sta" # ИСПРАВЛЕНО
    if state_file.exists():
        state_file.unlink()
        logger.info(f"Удалён state-файл: {state_file}") # ИСПРАВЛЕНО

def convert_time_from_ms_to_str(ts_ms:str):
    # Преобразуем строку в число и делим на 1000
    ts_sec = int(ts_ms) / 1000

    # Преобразование в локальное время
    return datetime.fromtimestamp(ts_sec).strftime('%Y-%m-%d %H:%M:%S')

def get_candle_color(open_p: float, close_p: float) -> str:
    """Библиотечная функция определения цвета свечи."""
    if close_p > open_p:
        return "Green"
    elif close_p < open_p:
        return "Red"
    return "Neutral"

def round_to_step(qty_float, qty_step_float):
    """
    Универсальное округление к шагу с использованием Decimal для точности.
    """
    qty_d = Decimal(str(qty_float))
    qty_step_d = Decimal(str(qty_step_float))

    # 1. Нормализация: Делим qty_d на шаг
    normalized = qty_d / qty_step_d
    
    # 2. Округление: Округляем до ближайшего целого (используя round() для Decimal)
    #    Обратите внимание: Decimal.to_integral() округляет до целого
    #    в соответствии с заданным методом округления (ROUND_HALF_UP).
    #    Для простоты можно использовать обычный round() для float, но
    #    для полной чистоты используем to_integral()
    rounded_normalized = normalized.to_integral(rounding=ROUND_HALF_UP)
    
    # 3. Денормализация: Умножаем обратно на шаг
    final_qty_d = rounded_normalized * qty_step_d
    
    return float(final_qty_d)

def calculate_pnl(side: str, entry_price: float, current_price: float, size: float) -> float:
    """
    Чистая математика расчета PnL. 
    Можно использовать в любом боте.
    """
    if size <= 0 or current_price <= 0:
        return 0.0
    
    mult = 1 if side.lower() == 'buy' else -1
    return (current_price - entry_price) * size * mult

def is_level_crossed_bidirectional(
    prev_price: float,
    price: float,
    level: float
) -> bool:

    return (
        (prev_price <= level <= price)
        or
        (price <= level <= prev_price)
    )    
    
