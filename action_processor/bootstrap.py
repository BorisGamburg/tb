from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
from typing import TYPE_CHECKING

from rich.console import Console
from rich.logging import RichHandler

from utils.telegram import Telegram
from proxy_server.proxy_driver import ProxyDriver
from common.price_service import PriceService

if TYPE_CHECKING:
    from action_processor.notifier import Notifier


# CONTEXTS
@dataclass(slots=True)
class DirCtx:
    project_root_dir: Path
    log_dir: Path
    state_dir: Path
    config_dir: Path

@dataclass(slots=True)
class AppContext:
    logger: logging.Logger
    trade_logger: logging.Logger

    telegram: Telegram
    proxy_driver: ProxyDriver
    price_service: PriceService

    config_file: Path

    console: Console

    dir_ctx: DirCtx
    notifier: Notifier | None = None

# Подготавливаем каталоги проекта: root, log, state, config 
def prepare_dirs(
    project_root_dir: Path | None = None
) -> DirCtx:
    if project_root_dir is None:
        project_root_dir = (
            Path(__file__)
            .resolve()
            .parent
            .parent
            .parent
        )

    log_dir = project_root_dir / "data" / "log"
    state_dir = project_root_dir / "data" / "state"
    config_dir = project_root_dir / "data" / "config"

    log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    state_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    config_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return DirCtx(
        project_root_dir=project_root_dir,
        log_dir=log_dir,
        state_dir=state_dir,
        config_dir=config_dir,
    )

# Инициализируем инфраструктуру приложения: логгеры, телеграм, прокси
def init_infrastruct(
    config_file_rel_path: str,
) -> AppContext:
    # Подготавливаем каталоги проекта: root, log, state, config
    dir_ctx = prepare_dirs()

    # Собираем полный путь к конфигурационному файлу
    config_file = (
        dir_ctx.config_dir /
        config_file_rel_path
    )    

    console = Console()

    # Инициализируем логгеры
    logger, trade_logger = init_loggers(config_file_rel_path, dir_ctx, console)

    # Инициализируем телеграм
    telegram = init_telegram(dir_ctx, logger)

    # Инициализируем прокси драйвер
    proxy_driver = ProxyDriver(
        logger=logger
    )

    price_service = PriceService(
        proxy_driver=proxy_driver
    )

    # Возвращаем контекст приложения
    return AppContext(
        logger=logger,
        trade_logger=trade_logger,
        telegram=telegram,
        proxy_driver=proxy_driver,
        price_service=price_service,
        config_file=config_file,
        console=console,
        dir_ctx=dir_ctx,
    )

def init_telegram(dir_ctx, logger):
    telegram_config_file = (
        dir_ctx.config_dir /
        "telegram_config.txt"
    )

    telegram = Telegram(
        logger=logger,
        config_file=telegram_config_file,
    )
    return telegram

def init_loggers(config_file_rel_path, dir_ctx, console):
    rel_path = Path(config_file_rel_path)

    # Создаем подкаталог конкретного инструмента внутри data/log/ (например, data/log/CHILLGUYUSDT/)
    instrument_log_dir = dir_ctx.log_dir / rel_path.parent
    instrument_log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    config_tag = rel_path.stem

    logger = setup_logger(
        config_tag=config_tag,
        log_dir=instrument_log_dir,
        console=console
    )

    trade_logger = setup_trade_logger(
        config_tag=config_tag,
        log_dir=instrument_log_dir,
        console=console
    )
    return logger,trade_logger

# ============================================================
# LOGGER
# ============================================================

def setup_logger(
    config_tag: str,
    log_dir: Path,
    console: Console,
) -> logging.Logger:

    logger = logging.getLogger(
        config_tag
    )

    # защита от повторного создания handlers
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    # =========================
    # CONSOLE (RICH)
    # =========================

    rich_handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        markup=False,
        show_time=True,
        show_level=True,
        show_path=False,
        log_time_format="[%d.%m.%Y %H:%M:%S]",
    )

    rich_handler.setFormatter(
        logging.Formatter(
            "%(message)s"
        )
    )    

    logger.addHandler(
        rich_handler
    )

    # =========================
    # FILE LOG
    # =========================

    log_file_path = log_dir / f"{config_tag}.log"
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(
        log_file_path,
        encoding="utf-8",
    )

    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            "%d %H:%M:%S",
        )
    )

    logger.addHandler(
        file_handler
    )

    # =========================
    # THIRD PARTY LOGGERS
    # =========================

    websocket_logger = logging.getLogger(
        "websocket"
    )

    websocket_logger.setLevel(
        logging.WARNING
    )

    pybit_logger = logging.getLogger(
        "pybit"
    )

    pybit_logger.setLevel(logging.WARNING)

    return logger


# ============================================================
# TRADE LOGGER
# ============================================================

def setup_trade_logger(
    config_tag: str,
    log_dir: Path,
    console: Console,
) -> logging.Logger:

    trade_logger = logging.getLogger(
        f"{config_tag}_trades"
    )

    if trade_logger.handlers:
        return trade_logger

    trade_logger.setLevel(
        logging.INFO
    )

    trade_logger.propagate = False

    # [УДАЛЕНЫ 14 СТРОК НИЖЕ] (Было: блок CONSOLE (RICH), добавлявший RichHandler в trade_logger)

    # =========================
    # FILE LOG
    # =========================

    trade_log_path = log_dir / f"{config_tag}_trades.log"
    trade_log_path.parent.mkdir(parents=True, exist_ok=True)

    is_new_file = not trade_log_path.exists() or trade_log_path.stat().st_size == 0

    file_handler = logging.FileHandler(
        trade_log_path,
        encoding="utf-8",
    )

    file_handler.setFormatter(
        logging.Formatter("%(message)s")
    )

    trade_logger.addHandler(file_handler)

    if is_new_file:
        header = (
            f"===================================================================================================================================================\n"
            f"TIMESTAMP        | EVENT | SYMBOL       | SIDE | LVL | QTY     | EXEC_PRICE | ENTRY_PRICE| GROSS_USD ($) | GROSS_% | FEES ($)  | NET_USD ($)  | NET_%  | REASON\n"
            f"==================================================================================================================================================="
        )
        trade_logger.info(header)

    return trade_logger
