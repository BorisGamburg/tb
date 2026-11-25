from __future__ import annotations
from pathlib import Path
import sys
import logging
import threading
import time
from prog.utils.telegram import Telegram
from prog.drivers.bybit_driver import BybitDriver
from prog.proxy_server.proxy_driver import ProxyDriver
from prog.managers.account_loader import load_account

class SharedProxy:
    def __init__(
        self,
        account_name: str,
        config_tag: str,
    ):
        self.config_tag = config_tag
        self.account = load_account(account_name)
        
        self.project_root = Path(__file__).resolve().parent.parent.parent
        
        # Инициализация путей
        self.log_dir = self.project_root / "data" / "log"
        self.state_dir = self.project_root / "data" / "state"
        self.config_dir = self.project_root / "data" / "config"
        self._prepare_paths()

        # Инициализация сервисов
        self.logger = self._setup_logger()
        self._tg_lock = threading.Lock()
        self._tg_last_global = 0.0
        self._tg_last_by_key = {}
        self._install_thread_excepthook()

        self.log_account(account_name)        

        telegram_config_path = self.config_dir / "telegram_config.txt"
        self.telegram = Telegram(logger=self.logger, config_file=telegram_config_path)

        self.exchange_driver = BybitDriver(
            demo=self.account.demo,
            api_key=self.account.api_key,
            api_secret=self.account.api_secret,
            telegram=self.telegram,
            logger=self.logger,
        )

        self.prov_serv = ProxyDriver(logger=self.logger)
        self.full_config_path = self.config_dir / f"{config_tag}.toml"

    # --- Анти-спам для Telegram-алертов ---
    TG_KEY_COOLDOWN = 3600   # сек: один и тот же ключ не чаще раза в час
    TG_GLOBAL_MIN_GAP = 30   # сек: между любыми двумя алертами (шторм одновременных застываний)

    def telegram_alert(self, key: str, text: str, force: bool = False) -> bool:
        """Отправка в Telegram с ограничением частоты, в фоне. Возвращает True, если отправлено.
        force=True обходит лимит по ключу (но не глобальный)."""
        now = time.time()
        with self._tg_lock:
            if now - self._tg_last_global < self.TG_GLOBAL_MIN_GAP:
                return False
            if not force and now - self._tg_last_by_key.get(key, 0.0) < self.TG_KEY_COOLDOWN:
                return False
            self._tg_last_global = now
            self._tg_last_by_key[key] = now
        threading.Thread(
            target=self.telegram.send_telegram_message, args=(text,), daemon=True
        ).start()
        return True

    def log_account(self, account_name):
        mode = "🟡 DEMO" if self.account.demo else "🔴 REAL"
        self.logger.info("════════════════════════════════════")
        self.logger.info(f"Account : {account_name}")
        self.logger.info(f"Mode    : {mode}")
        self.logger.info("════════════════════════════════════")

    def _prepare_paths(self):
        for d in [self.log_dir, self.state_dir, self.config_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _setup_logger(self) -> logging.Logger:
        l = logging.getLogger(self.config_tag)
        l.setLevel(logging.INFO)
        l.propagate = False

        formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%d %H:%M:%S")

        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        l.addHandler(ch)

        fh = logging.FileHandler(self.log_dir / f"{self.config_tag}.log", encoding="utf-8")
        fh.setFormatter(formatter)
        l.addHandler(fh)

        # pybit и websocket-client пишут причины обрыва WS (error, "will no longer
        # try to reconnect") в свои логгеры. Без обработчиков эти сообщения уходят
        # в stderr и теряются, поэтому направляем их в тот же лог.
        for name in ("websocket", "pybit"):
            ext = logging.getLogger(name)
            ext.setLevel(logging.WARNING)
            ext.addHandler(ch)
            ext.addHandler(fh)
            ext.propagate = False

        return l

    def _install_thread_excepthook(self):
        """Исключения в фоновых потоках (в т.ч. WS pybit) иначе уходят только в stderr."""
        def hook(args):
            if args.exc_type is SystemExit:
                return
            thread_name = args.thread.name if args.thread else "?"
            self.logger.error(
                f"❌ Необработанное исключение в потоке '{thread_name}': "
                f"{args.exc_type.__name__}: {args.exc_value}",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )

        threading.excepthook = hook