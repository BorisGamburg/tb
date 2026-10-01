from dataclasses import dataclass

from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_resolver.grid_mtf_strategy.grid_mtf_map_mng import GridMTFMapMng
from action_processor.bootstrap import AppContext
from action_resolver.grid_mtf_strategy.partial_exit_cross import PartialExitCross
from action_resolver.grid_mtf_strategy.breakeven_checker import BreakevenChecker
from action_resolver.grid_mtf_strategy.partial_exit_bbw import PartialExitBBW, BBWCheckDetails
from action_resolver.grid_mtf_strategy.profit_filter import ProfitFilter
from action_resolver.grid_mtf_strategy.rearm_manager import RearmMng, RearmCheckResult
from common.trading_info import TradingInfo
from action_processor.action_service import ActionService
from action_processor.action import Action, ActionCommand, ActionDetails
from utils.utils import get_inverse_side
from action_resolver.grid_mtf_strategy.merge_levels import MergeLevels
from action_resolver.grid_mtf_strategy.entry_manager import EntryMng
from action_resolver.grid_mtf_strategy.entry_checker import EntryCheckResult, EntryCheckDetails
from action_processor.action_guard import ActionGuard, GuardResult
from action_resolver.grid_mtf_strategy.status_line import StatusLine
from action_processor.execution.execution_result import ExecutionResult
from action_resolver.resolve_result import ResolveResult

@dataclass
class BBWExitResult:
    signal: bool
    execution_result: ExecutionResult | None

@dataclass
class CrossExitResult:
    signal: bool
    execution_result: ExecutionResult | None    

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
            trading_info=trading_info,
        )        

        self.merge_levels = MergeLevels(
            state_store=self.state_store,
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
            side=self.side,
        )        

        self._started = False

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

        self.entry_manager = EntryMng(
            state_store=self.state_store,
            map_mng=self.map_mng,
            app_ctx=app_ctx,
            trading_info=self.trading_info,
            action_service=self.action_service,
        )

        self.partial_exit_bbw = PartialExitBBW(
            state_store=self.state_store,
            proxy_driver=self.proxy_driver,
            price_service=self.price_service,
            map_mng=self.map_mng,
            side=self.side,
            symbol=self.symbol,
        )             

        self.rearm_manager = RearmMng(
            state_store=self.state_store,
            map_mng=self.map_mng,
            proxy_driver=self.proxy_driver,
            price_service=self.price_service,
            logger=self.logger,
            symbol=self.symbol,
            side=self.side,
            trading_info=self.trading_info,
            action_service=self.action_service,
        )                

        self.action_guard = ActionGuard(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
            side=self.side,
            logger=self.logger,
            telegram=app_ctx.telegram,
            state_store=self.state_store,
        )

        self.profit_filter = ProfitFilter(
            price_service=self.price_service,
            symbol=self.symbol,
            side=self.side,
            fee_taker=self.trading_info.fee_taker,
        )

        self.status_line = StatusLine()

        self._log_parameters()

    def _log_parameters(self) -> None:
        data = self.state_store.data
        params = (
            f"Symbol: {data.symbol}\n"
            f"Side: {data.side}\n"
            f"Strategy: {data.strategy}\n"
            f"Min rearm distance: {data.min_rearm_distance_pct}\n"
            f"Min profit: {data.min_profit_pct}\n"
            f"Max profit BB: {data.max_profit_bb_pct}%\n"
            f"Merge threshold: {data.merge_threshold_pct}%\n"            
            f"Sleep interval: {data.sleep_interval}\n"
        )
        self.app_ctx.logger.info(params)

    def resolve(
        self,
    ) -> ResolveResult:
         # Проверяем есть ли группа маленьких уровней для merge.
        # Если есть -> объединяем все уровни группы
        merged = self.merge_levels.merge_multiple_levels()

        # Если было соединение уровней -> выходим
        if merged:
            return ResolveResult(
                executed=True,
                status=self._get_status_line(),
            )

        # Если закрывать нельзя -> выходим        
        guard_result = self.is_exit_allowed()
        if not guard_result.allowed:
            return ResolveResult(
                executed=False,
                status=self._get_status_line(
                    guard_result=guard_result,
                ),
            )
        
        # Запускаем стратегию
        (
            exec_result,
            check_result,
            entry_check_details,
            rearm_check_result,
            bbw_check_details,
        ) = self._resolve_action()

        if exec_result is not None:
            executed = exec_result.executed
        else:
            executed = False

        status = self._get_status_line(
            check_result,
            entry_check_details,
            rearm_check_result,
            bbw_check_details,
            guard_result,
        )

        return ResolveResult(
            executed=executed,
            status=status,
        )
    
    def _execute_close(
        self,
        entry,
        reason: str,
        details: ActionDetails | None = None,
    ) -> ExecutionResult:
        action_command = ActionCommand(
                action=Action.CLOSE,
                symbol=self.symbol,
                levels=[entry],
                side=get_inverse_side(self.side),
                qty=entry.qty,
                reason=reason,
                details=details,
            )

        return self.action_service.process_action(
                action_command,
            )

    def _resolve_exit_cross(
        self,
    ) -> CrossExitResult:
        should_exit, entry, cross_exit_details = self.partial_exit_cross.check()

        if should_exit:
            exec_result = self._execute_close(
                entry,
                reason="cross",
                details=ActionDetails(cross_exit=cross_exit_details)
            )

            return CrossExitResult(
                signal=True,
                execution_result=exec_result,
            )

        return CrossExitResult(
            signal=False,
            execution_result=None,
        )

    def _resolve_entry(
        self,
    ) -> tuple[
        ExecutionResult | None,
        EntryCheckResult,
        EntryCheckDetails,
    ]:
        return self.entry_manager.resolve()

    def _execute_bbw_exit(
        self,
        entry,
        bbw_check_details: BBWCheckDetails,
    ) -> tuple[ExecutionResult, RearmCheckResult | None]:
        exec_result = self._execute_close(
            entry,
            reason="bbw",
            details=ActionDetails(
                bbw_exit=bbw_check_details,
            ),
        )

        if not exec_result.executed:
            return exec_result, None

        rearm_result, rearm_check_result = (
            self.rearm_manager._resolve_rearm(
                initial_qty=entry.initial_qty
            )
        )

        if rearm_result is not None:
            exec_result = rearm_result

        return exec_result, rearm_check_result

    def _resolve_bbw_exit(
        self,
    ) -> tuple[
        BBWExitResult,
        RearmCheckResult | None,
        BBWCheckDetails | None,
    ]:
        # Есть сигнал на выход?
        signal, entry, bbw_check_result, bbw_check_details = (
            self.partial_exit_bbw.check()
        )

        # Проверяем есть ли сигнал
        if not signal:
            return (
                BBWExitResult(
                    signal=False,
                    execution_result=None,
                ),
                None,
                bbw_check_details,
            )

        # Сигнал есть -> выполняем bbw_exit
        exec_result, rearm_check_result = self._execute_bbw_exit(
            entry,
            bbw_check_details,
        )

        return (
            BBWExitResult(
                signal=True,
                execution_result=exec_result,
            ),
            rearm_check_result,
            bbw_check_details,
        )

    def _resolve_action(
        self,
    ) -> tuple[
        ExecutionResult | None,
        EntryCheckResult | None,
        EntryCheckDetails | None,
        RearmCheckResult | None,
        BBWCheckDetails | None
    ]:
        # Выход по пересечению предыдущего уровня
        cross_exit_result = self._resolve_exit_cross()
        if cross_exit_result.signal:
            return (
                cross_exit_result.execution_result,
                None,
                None,
                None,
                None,
            )
                
        # Выход по BBW
        (
            bbw_exit_result,
            rearm_check_result,
            bbw_check_details,
        ) = self._resolve_bbw_exit()
        if bbw_exit_result.signal:
            return (
                bbw_exit_result.execution_result,
                None,
                None,
                rearm_check_result,
                bbw_check_details,
            )

        # Проверка на вход
        (
            exec_result,
            entry_check_result,
            entry_check_details,
        ) = self._resolve_entry()

        return (
            exec_result,
            entry_check_result,
            entry_check_details,
            None,
            bbw_check_details,
        )

    def _get_status_line(
        self,
        entry_check_result: EntryCheckResult | None = None,
        entry_check_details: EntryCheckDetails | None = None,
        rearm_check_result: RearmCheckResult | None = None,
        bbw_check_details: BBWCheckDetails | None = None,
        guard_result: GuardResult | None = None,
    ):
        last_price = self.proxy_driver.get_last_price(self.symbol)
        status_line = self.status_line.build(
            price=last_price,
            check_result=entry_check_result,
            check_details=entry_check_details,
            rearm_check_result=rearm_check_result,
            bbw_check_details=bbw_check_details,
            guard_result=guard_result,
        )
        return status_line
        
    def is_exit_allowed(self) -> GuardResult:
        """
        Проверяет, можно ли закрывать уровни сейчас.
        """
        if not self.state_store.data.exit_guard_enabled:
            return GuardResult(
                allowed=True,
            )

        return self.action_guard.is_allowed()    

