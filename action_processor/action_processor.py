import threading
from typing import Any
from action_processor.state.state import State 
from action_processor.execution.execution import Execution
from action_processor.accounting import Accounting
import time
from action_processor.bootstrap import AppContext
from rich.live import Live
from rich.text import Text
from action_processor.notifier import Notifier
from action_resolver.strategy_factory import StrategyFactory


class ActionProcessor:
    # Явное объявление типов для IDE и линтеров
    state_store: State
    execution: Execution
    accounting: Accounting
    strategy: Any

    def __init__(
        self,
        app_ctx: AppContext,
    ):
        # 1. Базовая конфигурация
        self.shutdown_event = threading.Event()
        self.iteration = 0
        self.app_ctx = app_ctx
        self.logger = app_ctx.logger
        self.proxy_driver = app_ctx.proxy_driver
        self.config_file_path = app_ctx.config_file
        self.telegram = app_ctx.telegram

        self.state_store, self.strategy = StrategyFactory.initialize(
            config_file=self.config_file_path,
            app_ctx=self.app_ctx,
        )

        # 4. Инициализация Execution
        self.execution = Execution(
            proxy_driver=self.proxy_driver,
            price_service=self.app_ctx.price_service,
            logger=self.logger,
        )

        # 5. Инициализация Accounting
        self.accounting = Accounting(
            state_store=self.state_store,
        )

        # 6. Инициализация Notifier
        self.notifier = Notifier(
            logger=self.logger,
            trade_logger=self.app_ctx.trade_logger,
            telegram=self.telegram,
            state_store=self.state_store,
        )

        # Логирование параметров при инициализации
        self.notifier.log_parameters()

    def run(self) -> None:
        self.iteration = 1
        self.notifier.log_iteration(self.iteration)
        try:
            with Live(
                Text(),
                console=self.app_ctx.console,
                refresh_per_second=10,
                screen=False,
            ) as self.live:
                while not self.shutdown_event.is_set():
                    # Стратегия
                    resolve_result = self.strategy.resolve(None)

                    # Получаем команду стратегии
                    cmd = resolve_result.action_command

                    # Если команда есть -> выполняем ее
                    if cmd:
                        self.notifier.notify_action(resolve_result.action_command)
                        self._exec_action(resolve_result)

                    # Обновляем строку статуса
                    self.live.update(resolve_result.status)

                    if not resolve_result.skip_sleep:
                        time.sleep(self.state_store.data.sleep_interval)

        except KeyboardInterrupt:
            self.logger.info("Остановлено пользователем")

        except Exception as e:
            self.logger.exception(f"Критическая ошибка: {e}")
            self.telegram.send_telegram_message(
                f"{self.state_store.data.symbol} | Ошибка: {e}"
            )

        finally:
            self.stop()

    def _exec_action(self, resolve_result):
        # Запускаем Executor
        exec_result = self.execution.execute(resolve_result.action_command)
        # Лог
        self.notifier.log_execution(exec_result)
        self.notifier.notify_telegram(exec_result)

        # Запускаем Accounter
        accounting_message = self.accounting.apply(exec_result)
        # Логи
        self.notifier.log(accounting_message)
        self.notifier.log_trade_table(exec_result)

        # Увеличиваем номер итерации
        self.iteration += 1

        # Логируем итерацию
        self.notifier.log_iteration(self.iteration)

    def stop(self) -> None:
        self.logger.info("Остановка TradeOverBot...")

        # Завершаем работу
        self.shutdown_event.set()

        # Сохраняем состояние при остановке
        self.state_store.save()
             
        self.logger.info("TradeOverBot остановлен.")

