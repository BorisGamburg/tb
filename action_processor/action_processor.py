import threading
from typing import Any
from action_processor.state.state import State 
from action_processor.execution.execution import Execution
from action_processor.accounting import Accounting
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
        self.previous_execution_result = None

        self.state_store, self.strategy = StrategyFactory.initialize(
            config_file=self.config_file_path,
            app_ctx=self.app_ctx,
        )        

        self._initialize_external_server()

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
        self.app_ctx.notifier = self.notifier


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
                    # Получаем внешнюю команду
                    external_command = self._get_external_command()

                    try:
                        # Полный цикл обработки команды
                        resolve_result = self._resolve_exec_account(external_command)

                        # Если команда пришла извне -> сообщаем результат
                        if external_command:
                            self.zmq_socket.send_json({
                                "success": True,
                                "message": "done",
                            })
                    except Exception as e:
                        if external_command:
                            self.zmq_socket.send_json({
                                "success": False,
                                "message": str(e),
                            })
                        raise

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

    def _resolve_exec_account(self, external_command):
        resolve_result = self.strategy.resolve(
            external_command, 
            execution_result=self.previous_execution_result,
        )

        cmd = resolve_result.action_command

        if cmd:
            self.notifier.notify_action(cmd)
            self._exec_action(resolve_result)

        return resolve_result

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

    def _exec_action(self, resolve_result):
        # Запускаем Executor
        exec_result = self.execution.execute(
            resolve_result.action_command
        )

        # Логируем результат попытки
        self.notifier.log_execution(exec_result)

        # Сохраняем результат последнего исполнения для использования в следующей итерации
        self.previous_execution_result = exec_result

        # Если ордер не был исполнен, выходим из функции
        if not exec_result.executed:
            return

        # Уведомляем о фактическом исполнении
        self.notifier.notify_telegram(exec_result)

        # Запускаем Accounter
        accounting_message = self.accounting.apply(exec_result)

        # Логируем результаты
        self.notifier.log(accounting_message)
        self.notifier.log_trade_table(exec_result)

        # Увеличиваем номер итерации
        self.iteration += 1
        self._on_iteration()             
