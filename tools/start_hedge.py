#!/usr/bin/env python3
"""
Скрипт запуска HedgeMng - системы управления хеджированием позиций.
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import Optional
from prog.hedge.hedge_mng import HedgeMng
from prog.proxy_server.proxy_driver import ProxyDriver
from prog.hedge.hedge_shared import HedgeShared
from prog.utils.telegram import Telegram
from prog.utils.utils import get_inverse_side
from prog.hedge.hedge_state import HedgeState
from pprint import pprint, pformat

# ==============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ==============================================================================

def get_config_param() -> Path:
    """Определяет путь к конфигу из аргументов командной строки"""
    # Ищем аргумент --config (например: python main.py --config aevo.toml)
    for i, arg in enumerate(sys.argv):
        if arg == "--config":
            return Path(sys.argv[i + 1])
         
    # Если аргумент не найден, выбрасываем исключение
    raise Exception("Аргумент --config не найден в командной строке.")


def path_init():
    #BASE_DIR = Path(__file__).resolve().parent.parent
    BASE_DIR = Path(__file__).resolve().parent
    print(f"BASE_DIR: {BASE_DIR}")
    CONFIG_DIR = BASE_DIR / "data" / "config"
    config_param = get_config_param()

    # Config file 
    config_file = f"{config_param}_hedge.toml"
    CONFIG_PATH = CONFIG_DIR / config_file
    
    # Log file
    log_file = f"{config_param}_hedge.log"
    LOG_FILE_PATH = BASE_DIR / "data" / "log" / log_file

    # State file
    state_file = f"{config_param}_hedge.log"
    STATE_FILE_PATH = BASE_DIR / "data" / "state" / state_file

    # Telegram config file
    TELEGRAM_CONFIG_PATH = CONFIG_DIR / "telegram_config.txt"

    # ПРОВЕРКА ПЕРЕД ЗАПУСКОМ
    if not CONFIG_PATH.exists():
        # Это выведет реальный путь, по которому скрипт ищет файл
        raise FileNotFoundError(f"\n❌ Файл конфигурации НЕ НАЙДЕН!\nОжидаемый путь: {CONFIG_PATH}\n"
                                f"Текущая рабочая директория: {os.getcwd()}")
                                
    return CONFIG_PATH,LOG_FILE_PATH,TELEGRAM_CONFIG_PATH, STATE_FILE_PATH

def main():
    """Главная функция запуска системы."""

    # Инициализация путей
    CONFIG_PATH, LOG_FILE_PATH, TELEGRAM_CONFIG_PATH, STATE_FILE_PATH = path_init()
    
    # читаем Settings
    settings = HedgeState(CONFIG_PATH)

    # Инициализация Shared
    shared_hedge = HedgeShared(
        log_file_path=LOG_FILE_PATH, 
        log_level=getattr(logging, settings.log_level.upper()),
        telegram_config_path=TELEGRAM_CONFIG_PATH
    )
    
    # Инициализация HedgeManager
    hedge_mng = HedgeMng(
        shared=shared_hedge, 
        hedge_state=settings,
        STATE_FILE_PATH=STATE_FILE_PATH
    )

    # ЛОГИРОВАНИЕ СТАРТА
    shared_hedge.logger.info("=" * 80)
    shared_hedge.logger.info("HEDGE MANAGER ЗАПУЩЕН")
    shared_hedge.logger.info("=" * 80)

    # ЛОГИРОВАНИЕ НАСТРОЕК
    log_settings(settings, shared_hedge)

    # ЗАПУСК
    try:
        hedge_mng.run() 
    except KeyboardInterrupt:
        shared_hedge.logger.info("Программа остановлена пользователем.")
    except Exception as e:
        shared_hedge.logger.critical(f"Непредвиденная ошибка при работе: {e}", exc_info=True)
        return 1
    finally:
        shared_hedge.logger.info("Завершение работы системы.")
        return 0

def log_settings(settings, hedge_shared):
    settings_dict = settings.model_dump(exclude={'hedge_orders', 'removed_orders'})

    # 2. Добавляем информацию о количестве (для справки)
    settings_dict['hedge_orders_count'] = len(settings.hedge_orders)
    settings_dict['removed_orders_count'] = len(settings.removed_orders)

    # 3. Красиво выводим через pformat
    hedge_shared.logger.info(f"\nТекущие настройки (кратко):\n{pformat(settings_dict, indent=4, width=80)}")


# ==============================================================================
# ТОЧКА ВХОДА
# ==============================================================================

if __name__ == '__main__':
    # sys.exit удаляем или оставляем, main() теперь вернет код выхода
    sys.exit(main())