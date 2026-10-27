from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_processor.bootstrap import AppContext
from common.trading_info import TradingInfo
from action_resolver.pyramid_strategy.pyramid_optimization_mng import (
    PyramidOptimizationMng,
)
from action_processor.action import Action
from action_processor.action import ActionCommand
from action_processor.action_service import ActionService
from action_resolver.resolve_result import ResolveResult
from action_resolver.pyramid_strategy.pyramid_entry_checker import (
    PyramidEntryChecker,
)
from action_resolver.pyramid_strategy.pyramid_partial_close_calculator import (
    PyramidPartialCloseCalculator,
)
from action_resolver.pyramid_strategy.pyramid_close_processor import (
    PyramidCloseProcessor,
)
from action_resolver.pyramid_strategy.pyr_tp_checker import PyrTPChecker



class PyramidStrategy(BaseStrategy):
    def __init__(
        self,
        state_store: State,
        app_ctx: AppContext,
        trading_info: TradingInfo,
    ):
        super().__init__()

        self.state_store = state_store
        self.app_ctx = app_ctx
        self.trading_info = trading_info

        self.close_checker = PyramidOptimizationMng(
            state=state_store,
            price_service=app_ctx.price_service,
            fee_taker=trading_info.fee_taker,
            logger=app_ctx.logger,
        )
        self.action_service = ActionService(
            app_ctx=app_ctx,
            state_store=state_store,
            trading_info=trading_info,
        )

        self.partial_close_calculator = PyramidPartialCloseCalculator()

        self.close_processor = PyramidCloseProcessor(
            action_service=self.action_service,
            partial_close_calculator=self.partial_close_calculator,
            trading_info=trading_info,
        )
        self.open_checker = PyramidEntryChecker(
            proxy_driver=app_ctx.proxy_driver,
            symbol=state_store.data.symbol,
            side=state_store.data.side,
            entry_tf=state_store.data.entry_tf,
            step_pct=float(state_store.data.open_step_pct),
            qty_pct=float(state_store.data.open_qty_pct),
            trading_info=trading_info,
        )

        self.profit_close_checker = PyrTPChecker(
            proxy_driver=app_ctx.proxy_driver,
            symbol=state_store.data.symbol,
            side=state_store.data.side,
            entry_tf=state_store.data.entry_tf,
            price_service=app_ctx.price_service,
            fee_taker=trading_info.fee_taker,
        )

    def resolve(self) -> ResolveResult:
        # Проверяем закрытие всей пирамиды по прибыли
        profit_close_result, profit_close_found = self._process_profit_close()
        if profit_close_found:
            return profit_close_result

        # Проверяем Unbind
        close_result, close_found = self._process_close()
        if close_found:
            return close_result

        # Проверяем открытие
        return self._process_open()

    def _process_open(self) -> ResolveResult:
        # Проверяем сигнал на открытие
        entry_result = self.open_checker.check(
            self.state_store.data.stack.entries
        )
        if not entry_result.allowed:
            return ResolveResult(executed=False, status="")

        # Формируем команду
        action_command = ActionCommand(
            action=Action.OPEN,
            symbol=self.state_store.data.symbol,
            side=self.state_store.data.side,
            qty=entry_result.qty,
        )

        # Передаем команду на исполнение и учет
        exec_result = self.action_service.process_action(action_command)

        # Возвращаем результат
        return ResolveResult(
            executed=exec_result.executed,
            status="",
        )

    def _process_close(self) -> tuple[ResolveResult, bool]:
        # Проверяем закрытие
        close_result = self.close_checker.check()
        if not close_result.found:
            return ResolveResult(executed=False, status=""), False

        # Формируем команду
        action_command = ActionCommand(
            action=Action.CLOSE,
            symbol=self.state_store.data.symbol,
            side=self.state_store.data.side,
            qty=close_result.qty,
            levels=[close_result.losing_level, close_result.profitable_level],
        )

        # Передаем команду на исполнение и учет
        exec_result = self.close_processor.execute(action_command)

        # Возвращаем результат
        return ResolveResult(
            executed=exec_result.executed,
            status="",
        ), True

    def _process_profit_close(self) -> tuple[ResolveResult, bool]:
        # Проверяем HA-разворот и достаточную прибыль
        entries = self.state_store.data.stack.entries
        if not self.profit_close_checker.check(entries):
            return ResolveResult(executed=False, status=""), False

        # Закрываем всю позицию
        action_command = ActionCommand(
            action=Action.CLOSE_POSITION,
            symbol=self.state_store.data.symbol,
            side=self.state_store.data.side,
            reason="PYRAMID_PROFIT_CLOSE",
        )

        exec_result = self.action_service.process_action(action_command)

        return ResolveResult(
            executed=exec_result.executed,
            status="",
        ), exec_result.executed