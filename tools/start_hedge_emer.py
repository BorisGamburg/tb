#!/usr/bin/env python3
import os
import sys
import time
import logging
from pathlib import Path
from pprint import pformat

# Твои существующие драйверы и классы состояния
from prog.proxy_server.proxy_driver import ProxyDriver
from prog.hedge_emergency.hedge_mng import HedgeMng
from prog.hedge_emergency.hedge_state import HedgeState

def get_config_param() -> str:
    """Определяет имя конфига из аргументов командной строки."""
    for i, arg in enumerate(sys.argv):
        if arg == "--config":
            return sys.argv[i + 1]
    raise Exception("❌ Ошибка: Аргумент --config не найден. Использование: python main.py --config opusdt")

def path_init():
    """Инициализация путей на основе имени конфигурации."""
    # Определяем корневую директорию проекта (prog/..)
    BASE_DIR = Path(__file__).resolve().parent
    CONFIG_DIR = BASE_DIR / "data" / "config"
    
    config_name = get_config_param()

    # Формируем пути
    CONFIG_PATH = CONFIG_DIR / f"{config_name}.toml"
    LOG_FILE_PATH = BASE_DIR / "data" / "log" / f"{config_name}.log"
    STATE_FILE_PATH = BASE_DIR / "data" / "state" / f"{config_name}.log"
    
    # Создаем директории, если их нет
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"❌ Файл конфигурации НЕ НАЙДЕН: {CONFIG_PATH}")
                                
    return CONFIG_PATH, LOG_FILE_PATH, STATE_FILE_PATH

def setup_logging(log_path: Path):
    """Настройка логирования: файл + консоль."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger("Main")

def main():
    """Точка входа."""
    try:
        # 1. Пути
        CONFIG_PATH, LOG_FILE_PATH, STATE_FILE_PATH = path_init()
        
        # 2. Логирование
        logger = setup_logging(LOG_FILE_PATH)
        
        # 3. Загрузка состояния (настроек)
        # Ожидаем в HedgeState поля: symbol, warning_fl, panic_fl, emergency_fl, hysteresis
        settings = HedgeState(CONFIG_PATH)
        
        # 4. Драйвер связи с прокси
        proxy_driver = ProxyDriver(logging.getLogger("Proxy"))

        # 5. Инициализация менеджера хеджирования
        hedge_mng = HedgeMng(
            hedge_state=settings, 
            proxy_driver=proxy_driver,
            state_file_path=STATE_FILE_PATH
        )

        logger.info("=" * 60)
        logger.info(f"🚀 СТАРТ HEDGE MANAGER | SYMBOL: {settings.symbol}")

        levels = settings.levels
        logger.info(
            "Пороги: " +
            " | ".join(f"{lvl.name.upper()}:{lvl.threshold}" for lvl in levels)
        )

        logger.info("=" * 60)

        # 6. Запуск основного цикла
        hedge_mng.run()

    except KeyboardInterrupt:
        logging.getLogger("Main").info("⏹ Программа остановлена пользователем.")
        return 0
    except Exception as e:
        # Ошибки не прячем, вываливаем всё в лог и падаем
        logging.getLogger("Main").critical(f"💥 КРИТИЧЕСКИЙ СБОЙ: {e}", exc_info=True)
        return 1
    finally:
        logging.getLogger("Main").info("Работа завершена.")

if __name__ == '__main__':
    sys.exit(main())