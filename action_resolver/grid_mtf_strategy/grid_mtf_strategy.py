from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_resolver.grid_mtf_strategy.grid_mtf_map_mng import GridMTFMapMng
from action_processor.bootstrap import AppContext
from action_resolver.grid_mtf_strategy.partial_exit_cross import PartialExitCross
from action_resolver.grid_mtf_strategy.breakeven_checker import BreakevenChecker
from action_resolver.grid_mtf_strategy.entry_checker import EntryChecker
from action_resolver.grid_mtf_strategy.partial_exit_bbw import PartialExitBBW
from action_resolver.grid_mtf_strategy.profit_filter import ProfitFilter
from dataclasses import dataclass, field
from action_resolver.grid_mtf_strategy.rearm_checker import RearmChecker
from rich.text import Text
from common.trading_info import TradingInfo
from action_processor.action_guard import ActionGuard
from action_processor.action_service import ActionService
from action_processor.process_result import ProcessResult
from action_processor.action import Action, ActionCommand
from utils.utils import get_inverse_side
from action_processor.action_source import ActionSource


@dataclass(slots=True)
class GridMTFRuntime:
    rearm_status: Text = field(
        default_factory=lambda: Text("OFF", style="dim")
    )
    rsi_exit_status: Text = field(
        default_factory=lambda: Text("N/A", style="dim")
    )
    rsi_entry_status: Text = field(
        default_factory=lambda: Text("N/A", style="dim")
    )
    bbw_exit_status: Text = field(
        default_factory=lambda: Text("N/A", style="dim")
    )
    ha_entry_status: Text = field(
        default_factory=lambda: Text("N/A", style="dim")
    )
    distance_status: Text = field(
        default_factory=lambda: Text("N/A", style="dim")
    )
    distance_entry_status: str = "N/A"
    guard_status: Text | None = None

class GridMTFStrategy(BaseStrategy):

    def __init__(
        self,
        state_store: State,
        map_mng: GridMTFMapMng,
        app_ctx: AppContext,
        trading_info: TradingInfo
    ):
        super().__init__()

        self.state_store = state_store
        self.symbol = state_store.data.symbol
        self.side = state_store.data.side
        self.proxy_driver = app_ctx.proxy_driver
        self.price_service = app_ctx.price_service
        self.logger = app_ctx.logger
        self.map_mng = map_mng
        self.trading_info = trading_info
        self.app_ctx = app_ctx

        self.action_service = ActionService(
            app_ctx=app_ctx,
            state_store=state_store,
        )        

        # sleep (можешь заменить на свою политику)
        self.sleep_interval = 5.0

        self._started = False

        self.runtime = GridMTFRuntime()

        # Инициализируем модуль проверки выхода на безубыток
        self.breakeven_checker = BreakevenChecker(
            fee_taker=self.trading_info.fee_taker,
            side=self.side,
        )

        self.partial_exit_cross = PartialExitCross(
            state_store=self.state_store,
            price_service=self.price_service,
            side=self.side,
            symbol=self.symbol,
            breakeven_checker=self.breakeven_checker,
        )    

        self.entry_checker = EntryChecker(
            runtime=self.runtime,
            state_store=self.state_store,
            map_mng=self.map_mng,
            proxy_driver=self.proxy_driver,
            price_service=self.price_service,
            symbol=self.symbol,
            side=self.side,
        )     

        self.partial_exit_bbw = PartialExitBBW(
            runtime=self.runtime,
            state_store=self.state_store,
            proxy_driver=self.proxy_driver,
            price_service=self.price_service,
            map_mng=self.map_mng,
            side=self.side,
            symbol=self.symbol,
        )             

        self.rearm_checker = RearmChecker(
            runtime=self.runtime,
            state_store=self.state_store,
            map_mng=self.map_mng,
            proxy_driver=self.proxy_driver,
            price_service=self.price_service,
            logger=self.logger,
            symbol=self.symbol,
            side=self.side,
            trading_info=self.trading_info
        )                

        self.action_guard = ActionGuard(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
            side=self.side,
            logger=self.logger,
            telegram=app_ctx.telegram,
            runtime=self.runtime,
            state_store=self.state_store,
        )

        self.profit_filter = ProfitFilter(
            price_service=self.price_service,
            symbol=self.symbol,
            side=self.side,
            fee_taker=self.trading_info.fee_taker,
        )

        self._log_parameters()

    def _get_status_line(self):
        last_price = self.proxy_driver.get_last_price(self.symbol)
        status_line = self._build_status_line(last_price)
        return status_line

    def _build_status_line(
        self,
        price: float,
    ) -> Text:

        text = Text()
        text.append(f"PRICE: {price:.6f}  ", style="cyan")

        text.append("\nENTRY | HA: ", style="cyan")
        text.append(self.runtime.ha_entry_status)

        text.append(" | RSI: ", style="cyan")
        text.append(self.runtime.rsi_entry_status)

        text.append("\nEXIT  | RSI: ", style="cyan")
        text.append(self.runtime.rsi_exit_status)

        text.append(" | BBW: ", style="cyan")
        text.append(self.runtime.bbw_exit_status)

        if self.runtime.guard_status is not None:
            text.append("\nGUARD | ", style="cyan")
            text.append(self.runtime.guard_status)

        return text

    def _log_parameters(self) -> None:
        data = self.state_store.data
        params = (
            f"Symbol: {data.symbol}\n"
            f"Side: {data.side}\n"
            f"Strategy: {data.strategy}\n"
            f"Min rearm distance: {data.min_rearm_distance_pct}\n"
            f"Min profit: {data.min_profit_pct}\n"
            f"Max profit: {data.max_profit_pct}\n"
            f"Sleep interval: {data.sleep_interval}\n"
        )
        self.app_ctx.logger.info(params)

    def is_exit_allowed(self) -> bool:
        """
        Проверяет, можно ли закрывать уровни сейчас.
        """
        if not self.state_store.data.exit_guard_enabled:
            self.runtime.guard_status = None
            return True

        return self.action_guard.is_allowed()

    def resolve(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
            is_allowed = self.is_exit_allowed()
            status_line = self._get_status_line()
            process_result.status = status_line

            if not is_allowed:
                process_result.executed = False
                return process_result

            return self._resolve_action(
                process_result,
            )

    def _resolve_action(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        # Выход по пересечению предыдущего уровня
        process_result = self._resolve_exit_cross(
            process_result,
        )
        if process_result.signal:
            return process_result
        
                
        # Выход по BBW
        process_result = self._resolve_bbw_exit(
            process_result,
        )
        if process_result.signal:
            return process_result


        # Проверка на вход
        process_result = self._resolve_entry(
            process_result,
        )


        return process_result

    def _get_rearm_qty(self) -> float:
        level = len(self.state_store.stack_mng.data.entries)

        cur_map_elem = self.map_mng.get_template_by_level(level)
        qty_factor = cur_map_elem.qty_pct / 100

        balance = self.proxy_driver.get_balance()
        price = self.proxy_driver.get_last_price(self.symbol)

        qty_in_usd = qty_factor * balance
        qty = qty_in_usd / price

        qty = self.trading_info.get_valid_order_qty(qty)

        if qty <= 0:
            raise RuntimeError(
                f"Invalid REARM qty: {qty} "
                f"(level={level}, qty_factor={qty_factor})"
            )

        return qty

    def _build_rearm_action(self) -> ActionCommand:
        qty = self._get_rearm_qty()

        return ActionCommand(
            action=Action.OPEN,
            symbol=self.symbol,
            side=self.side,
            qty=qty,
            reason="REARM",
            source=ActionSource.REARM_CHECKER
        )

    def _execute_rearm(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        action = self._build_rearm_action()

        process_result = self.action_service.process_action(
            action,
            process_result,
        )

        return process_result

    def _resolve_rearm(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        while True:
            # Проверяем, нужно ли выполнять REARM
            rearm_needed = self.rearm_checker.check()

            if not rearm_needed:
                # REARM не нужен -> выходим из цикла
                return process_result
            else:
                # REARM нужен -> выполняем его
                process_result = self._execute_rearm(
                    process_result,
                )

                # Проверяем, выполнен ли REARM
                if process_result.executed:
                    # REARM выполнен -> выходим из цикла
                    return process_result
                else:
                    # REARM не выполнен -> повторно проверяем условия
                    self.logger.warning(
                        "REARM не выполнен, повторная попытка..."
                    )    

    def _resolve_bbw_exit(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        # Есть сигнал на выход?
        process_result.signal, entry = self.partial_exit_bbw.check()
        if process_result.signal:
            # Сигнал на выход есть
            process_result = self._execute_close(
                entry,
                process_result,
                reason="bbw",
                source=ActionSource.PARTIAL_EXIT_BBW
            )

            # Выполнен ли CLOSE?
            if process_result.executed:
                # CLOSE выполнен -> запускаем REARM
                return self._resolve_rearm(
                    process_result,
                )
            else:
                # CLOSE не выполнен -> выходим
                return process_result
        else:
            # Сигнала на выход нет
            return process_result

    def _execute_close(
        self,
        entry,
        process_result: ProcessResult,
        reason: str,
        source: ActionSource,
    ) -> ProcessResult:
        # Сигнал есть -> запускаем CLOSE
        action = ActionCommand(
                action=Action.CLOSE,
                symbol=self.symbol,
                levels=[entry],
                side=get_inverse_side(self.side),
                qty=entry.qty,
                reason=reason,
                source=source
            )
        process_result = self.action_service.process_action(
                action,
                process_result,
            )
        return process_result

    def _get_entry_qty(self) -> float:
        level = len(self.state_store.stack_mng.data.entries)

        cur_map_elem = self.map_mng.get_template_by_level(level)
        qty_factor = cur_map_elem.qty_pct / 100

        balance = self.proxy_driver.get_balance()
        qty_in_usd = qty_factor * balance

        price = self.proxy_driver.get_last_price(self.symbol)

        qty = qty_in_usd / price

        qty = self.trading_info.get_valid_order_qty(qty)

        if qty <= 0:
            raise RuntimeError(
                f"Invalid OPEN qty: {qty} "
                f"(qty_factor={qty_factor})"
            )

        return qty    

    def _execute_open(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        action = ActionCommand(
            action=Action.OPEN,
            symbol=self.symbol,
            side=self.side,
            qty=self._get_entry_qty(),
            reason="ha_reversal",
            source=ActionSource.ENTRY_CHECKER
        )

        process_result = self.action_service.process_action(
            action,
            process_result,
        )

        return process_result    

    def _resolve_exit_cross(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        should_exit, entry = self.partial_exit_cross.check()

        if should_exit:
            return self._execute_close(
                entry,
                process_result,
                reason="cross",
                source=ActionSource.PARTIAL_EXIT_CROSS
            )

        return process_result    


    def _resolve_entry(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        entry_allowed = self.entry_checker.check()
        self.app_ctx.notifier.log_distance_blocked(self.runtime)

        if entry_allowed:
            return self._execute_open(
                process_result,
            )

        process_result.executed = False

        return process_result    