#!/usr/bin/env python3
"""
Скрипт запуска CynicalHedgeMng - системы управления "Циничным кулаком".
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import Optional
# ЗАМЕНА: Импортируем новый менеджер
from prog.hedge.cynical_hedge_mng import CynicalHedgeMng
from prog.proxy_server.proxy_driver import ProxyDriver
from prog.hedge.hedge_shared import HedgeShared
from prog.utils.telegram import Telegram
from prog.utils.utils import get_inverse_side
from prog.hedge.state import Settings
from pprint import pprint, pformat

# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

def get_config_param() -> Path:
    """Определяет путь к конфигу из аргументов командной строки"""
    for i, arg in enumerate(sys.argv):
        if arg == "--config":
            return Path(sys.argv[i + 1])
    raise Exception("Аргумент --config не найден. Пример: python main.py --config aevo")

def path_init():
    BASE_DIR = Path(__file__).resolve().parent
    CONFIG_DIR = BASE_DIR / "data" / "config"
    config_param = get_config_param()

    # Пути к файлам
    CONFIG_PATH = CONFIG_DIR / f"{config_param}_hedge.toml"
    LOG_FILE_PATH = BASE_DIR / "data" / "log" / f"{config_param}_hedge.log"
    TELEGRAM_CONFIG_PATH = CONFIG_DIR / "telegram_config.txt"

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"\n❌ Конфиг НЕ НАЙДЕН: {CONFIG_PATH}")
                                
    return CONFIG_PATH, LOG_FILE_PATH, TELEGRAM_CONFIG_PATH

# ==============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ==============================================================================

def main():
    """Главная функция запуска системы."""

    # 1. Инициализация путей
    CONFIG_PATH, LOG_FILE_PATH, TELEGRAM_CONFIG_PATH = path_init()
    
    # 2. Читаем настройки
    settings = Settings(CONFIG_PATH)

    # 3. Инициализация Shared (Логгер, Телеграм, Драйвер)
    shared_hedge = HedgeShared(
        log_file_path=LOG_FILE_PATH, 
        log_level=getattr(logging, settings.log_level.upper()),
        telegram_config_path=TELEGRAM_CONFIG_PATH,
        settings=settings
    )
    
    # 4. Инициализация НОВОГО менеджера
    hedge_mng = CynicalHedgeMng(shared=shared_hedge)

    # ЛОГИРОВАНИЕ СТАРТА
    shared_hedge.logger.info("=" * 80)
    shared_hedge.logger.info(f"CYNICAL HEDGE MANAGER ЗАПУЩЕН (Параметр: {get_config_param()})")
    shared_hedge.logger.info("=" * 80)

    # Вывод текущих настроек в лог
    log_settings(settings, shared_hedge)

    # 5. ЗАПУСК
    try:
        hedge_mng.run() 
    except KeyboardInterrupt:
        shared_hedge.logger.info("Программа остановлена пользователем.")
    except Exception as e:
        shared_hedge.logger.critical(f"Критический сбой: {e}", exc_info=True)
        return 1
    finally:
        shared_hedge.logger.info("Система выключена.")
        return 0

def log_settings(settings, hedge_shared):
    """Красивый вывод настроек в лог."""
    exclude = {'hedge_orders', 'removed_orders'}
    settings_dict = {k: v for k, v in settings.model_dump().items() if k not in exclude}
    settings_dict['active_hedges_count'] = len(settings.hedge_orders)
    
    hedge_shared.logger.info(f"\nНастройки лавины:\n{pformat(settings_dict, indent=4)}")


if __name__ == '__main__':
    sys.exit(main())