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
from action_processor.action_service import ActionService
from action_processor.external_command_processor import ExternalCommandProcessor
from action_processor.process_result import ProcessResult


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

        # 2. Инициализация стратегии и состояния
        self.state_store, self.strategy = StrategyFactory.initialize(
            config_file=self.config_file_path,
            app_ctx=self.app_ctx,
        )        

        # 3. Инициализация модуля для execution и accounting
        self.action_service = ActionService(
            app_ctx=self.app_ctx,
            state_store=self.state_store,
        )        

        # Инициализация модуля для обработки внешних команд
        self.external_command_processor = ExternalCommandProcessor(
            symbol=self.state_store.data.symbol,
            side=self.state_store.data.side,
            action_service=self.action_service,
            logger=self.logger,
        )   

        # 4. Инициализация ZMQ сервера для внешних команд
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
        self.notifier.log(
            self.notifier.build_stack_report()
        )   

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
                    process_result = ProcessResult()
                    self._process_cycle(process_result)

                    # Обновляем строку статуса 
                    self.live.update(process_result.status)

                    # Sleep, если не отменен
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

    def _process_cycle(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        # 1. Проверяем внешние команды
        process_result = self._process_external_logic(process_result)

        # Если внешней команды нет, продолжаем с внутренней логикой
        if process_result.external_command is None:
            process_result = self._process_internal_logic(process_result)

        # 2. Если было выполнено действие, увеличиваем итерацию и вызываем on_iteration
        if process_result.executed:
            self.iteration += 1
            self._on_iteration()

        # Возвращаем process_result 
        return process_result

    def _process_external_logic(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        external_command = self._get_external_command()

        if not external_command:
            return process_result

        process_result.external_command = external_command

        return self.external_command_processor.process(
            process_result,
        )

    def _process_internal_logic(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        process_result = self.strategy.resolve(process_result)

        return process_result