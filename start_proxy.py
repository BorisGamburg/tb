import os
import sys
from prog.proxy_server.shared_proxy import SharedProxy
from prog.proxy_server.proxy_server import ProxyServer
import argparse


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--account",
        required=True,
        help="Имя аккаунта (например bybit_test)",
    )

    parser.add_argument(
        "--config",
        default="provider",
        help="Имя конфигурации/инстанса",
    )

    return parser.parse_args()

if __name__ == "__main__":
    # Получаем аргументы комнадной строки
    args = parse_args()

    # 1. Инициализируем окружение
    shared_proxy = SharedProxy(
        account_name=args.account,
        config_tag=args.config,
    )

    # 2. Передаем объект shared_proxy в сервер
    server = ProxyServer(shared_proxy=shared_proxy)
    
    try:
        server.run()
    except KeyboardInterrupt:
        shared_proxy.logger.info("🛑 ProxyServer остановлен вручную.")
    finally:
        server.stop()