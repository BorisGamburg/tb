import argparse
from action_processor.action_processor import ActionProcessor
from action_processor.bootstrap import init_infrastruct


def parse_args() -> argparse.Namespace:
    """
    Парсим аргументы командной строки.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=str,
        required=True,
    )

    return parser.parse_args()

if __name__ == "__main__":
    # Парсим аргументы командной строки
    args = parse_args()

    # Инициализируем инфраструктуру приложения: логгеры, телеграм, прокси
    app_ctx = init_infrastruct(config_file_rel_path=args.config)

    # Создаем и запускаем процессор действий
    act_proc = ActionProcessor(app_ctx=app_ctx,)
    try:
        act_proc.run()
    except KeyboardInterrupt:
        app_ctx.logger.info("Прерывание от пользователя")
    finally:
        act_proc.stop()
        app_ctx.logger.info("Программа завершена.")
