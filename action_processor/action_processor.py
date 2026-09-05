import threading
from typing import Any
from action_processor.state.state import State 
import time
import zmq
from action_processor.bootstrap import AppContext
from rich.live import Live
from rich.text import Text
from action_processor.notifier import Notifier
from action_resolver.strategy_factory import StrategyFactory


class ActionProcessor:
    # Явное объявление типов для IDE и линтеров
    state_store: State
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

        self._initialize_external_server()

        # 6. Инициализация Notifier
        self.notifier = Notifier(
            logger=self.logger,
            trade_logger=self.app_ctx.trade_logger,
            telegram=self.telegram,
            state_store=self.state_store,
        )
        self.app_ctx.notifier = self.notifier


    def _get_external_command(self):
        if self.zmq_socket.poll(0):
            return self.zmq_socket.recv_json()

        return None

    def _get_external_endpoint(self):
        symbol = self.state_store.data.symbol
        strategy = self.state_store.data.strategy

        return f"ipc:///tmp/{symbol}_{strategy}.sock"

    def _initialize_external_server(self):
        self.zmq_context = zmq.Context()
        self.zmq_socket = self.zmq_context.socket(zmq.REP)
        self.zmq_socket.bind(self._get_external_endpoint())

    def stop(self) -> None:
        self.logger.info("Остановка TradeOverBot...")

        # Завершаем работу
        self.shutdown_event.set()

        # Сохраняем состояние при остановке
        self.state_store.save()
             
        self.logger.info("TradeOverBot остановлен.")

    def _on_iteration(self) -> None:
        self.notifier.log_iteration(self.iteration)

        on_iteration = getattr(self.strategy, "on_iteration", None)

        if on_iteration is not None:
            on_iteration()       

    def _process_internal_logic(self, external_command):
        resolve_result = self.strategy.resolve(
            external_command,
        )

        if resolve_result.executed:
            self.iteration += 1
            self._on_iteration()

        return resolve_result

    def run(self) -> None:
        self.iteration = 1
        self._on_iteration()

        try:
            with Live(
                Text(),
                console=self.app_ctx.console,
                refresh_per_second=10,
                screen=False,
            ) as self.live:
                while not self.shutdown_event.is_set():
                    # Логика цикла
                    resolve_result = self._process_cycle()

                    # Обновляем строку статуса 
                    self.live.update(resolve_result.status)

                    # Sleep, если не отменен
                    if not resolve_result.skip_sleep:
                        time.sleep(
                            self.state_store.data.sleep_interval
                        )

        except KeyboardInterrupt:
            self.logger.info("Остановлено пользователем")

        except Exception as e:
            self.logger.exception(f"Критическая ошибка: {e}")
            self.telegram.send_telegram_message(
                f"{self.state_store.data.symbol} | Ошибка: {e}"
            )

        finally:
            self.stop()

    def _process_external_command(self, external_command):
        try:
            resolve_result = self.strategy._handle_external_command(
                external_command
            )

            if resolve_result is not None:
                self.action_service.process_action(resolve_result)

            self.zmq_socket.send_json({
                "success": True,
                "message": "done",
            })

            return resolve_result

        except Exception as e:
            self.zmq_socket.send_json({
                "success": False,
                "message": str(e),
            })
            raise            

    def _process_cycle(self):
        # Определяем ветку: внешняя команда или внутренняя логика
        external_command = self._get_external_command()

        if external_command:
            # Обрабатываем внешнюю команду
            return self._process_external_command(
                external_command
            )

        # Отрабатываем внутреннюю логику
        return self._process_internal_logic(None)    