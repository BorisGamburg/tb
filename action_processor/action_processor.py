from action_processor.notifier import Notifier
from action_processor.accounting import Accounting
from action_processor.state.state import State
from action_resolver.strategy_factory import StrategyFactory
from action_processor.bootstrap import AppContext
from rich.live import Live
from rich.text import Text


class ActionProcessor:
    def __init__(self, app_ctx: AppContext):
        self.app_ctx = app_ctx
        self.logger = app_ctx.logger
        self.telegram = app_ctx.telegram

        # 1. Инициализация Strategy
        self.state_store, self.strategy = StrategyFactory.initialize(
            app_ctx=self.app_ctx,
        )

        # 2. Инициализация Accounting
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
        self.notifier.log_iteration(self.iteration)
        try:
            with Live(
                Text(),
                console=self.app_ctx.console,
                refresh_per_second=1,
            ) as live:
                while True:
                    result = self.strategy.resolve(self)
                    self.accounting.process(result)
                    self.notifier.process(result)
                    self.notifier.update_live(live)
                    self.iteration += 1
                    self.notifier.log_iteration(self.iteration)
        except KeyboardInterrupt:
            self.logger.info("Остановка по Ctrl+C")
