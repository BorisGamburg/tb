import logging
from pathlib import Path
from prog.managers.state_store_mng import StateStoreMng


def run_state_store_test():
    # Настройка логгера
    test_logger = logging.getLogger("StateStoreTest")
    test_logger.setLevel(logging.INFO)
    if not test_logger.handlers:
        ch = logging.StreamHandler()
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        ch.setFormatter(formatter)
        test_logger.addHandler(ch)

    test_config_file = Path("data/config/bat.toml")

    # 2. Инициализация и загрузка
    manager = StateStoreMng(test_config_file, test_logger)
    manager.load()

    # 4. Модификация данных
    NEW_RSI = 99
    manager.state_store.map["1"].at_rsi = NEW_RSI
    manager.state_store.symbol = "ETHUSDT"
    test_logger.info(f"Модификация: at_rsi[0] = {NEW_RSI}")

    # 5. Сохранение
    manager.save()


if __name__ == "__main__":
    run_state_store_test()