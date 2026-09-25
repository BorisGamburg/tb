from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_resolver.grid_mtf_strategy.grid_mtf_map_mng import GridMTFMapMng
from action_processor.bootstrap import AppContext
from action_resolver.grid_mtf_strategy.partial_exit_cross import PartialExitCross
from action_resolver.grid_mtf_strategy.breakeven_checker import BreakevenChecker
from action_resolver.grid_mtf_strategy.partial_exit_bbw import PartialExitBBW, BBWCheckResult
from action_resolver.grid_mtf_strategy.profit_filter import ProfitFilter
from action_resolver.grid_mtf_strategy.rearm_manager import RearmMng, RearmCheckResult
from rich.text import Text
from common.trading_info import TradingInfo
from action_processor.action_service import ActionService
from action_processor.process_result import ProcessResult
from action_processor.action import Action, ActionCommand
from utils.utils import get_inverse_side
from action_processor.action_source import ActionSource
from action_resolver.grid_mtf_strategy.merge_levels import MergeLevels
from action_resolver.grid_mtf_strategy.entry_manager import EntryMng
from action_resolver.grid_mtf_strategy.entry_checker import EntryCheckResult
from action_processor.action_guard import ActionGuard, GuardResult


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

        self._log_parameters()

    def _build_status_line(
        self,
        price: float,
        check_result: EntryCheckResult | None = None,
        rearm_check_result: RearmCheckResult | None = None,
        bbw_check_result: BBWCheckResult | None = None,
        guard_result: GuardResult | None = None,
    ) -> Text:

        text = Text()
        text.append(f"PRICE: {price:.6f}  ", style="cyan")

        text.append("\nENTRY | HA: ", style="cyan")
        if check_result is not None:
            ha = check_result.ha
            text.append(
                f"({ha.tf}m) [{ha.prev}→{ha.curr}]"
            )
            text.append(
                " ●",
                style="bold green" if ha.signal else "bold red",
            )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        text.append(" | RSI: ", style="cyan")
        if check_result is not None:
            rsi = check_result.rsi

            tf_th = (
                f"{rsi.threshold:.0f}"
                if rsi.threshold is not None
                else "N/A"
            )

            tf_v = (
                f"{rsi.value:.1f}"
                if rsi.value is not None
                else "N/A"
            )

            text.append(
                f"({tf_v}/{tf_th})"
                f" TF:{rsi.tf}"
            )
            text.append(
                " ●",
                style="bold green" if rsi.ok else "bold red",
            )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        text.append(" | BB: ", style="cyan")
        if check_result is not None:
            bb = check_result.bb

            text.append(
                f"({bb.value:.6f}/{bb.mid:.6f})"
                f" TF:{bb.tf}"
            )
            text.append(
                " ●",
                style="bold green" if bb.ok else "bold red",
            )
        else:
            text.append(
                "N/A",
                style="dim",
            )    

        text.append(" | DIST_THRES: ", style="cyan")
        if check_result is not None:
            distance = check_result.distance

            if distance.threshold is not None:
                text.append(
                    f"{distance.threshold:.6f}"
                )

                text.append(
                    " ●",
                    style=(
                        "bold green"
                        if distance.ok
                        else "bold red"
                    ),
                )
            else:
                text.append(
                    "N/A",
                    style="dim",
                )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        text.append("\nEXIT  | RSI: ", style="cyan")
        if rearm_check_result is not None:
            text.append(
                "OK" if rearm_check_result.rsi_ok else "BLOCK"
            )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        text.append(" | BBW: ", style="cyan")
        if bbw_check_result is not None:
            if not bbw_check_result.has_position:
                text.append(
                    "NO_POS",
                    style="dim",
                )
            elif bbw_check_result.take_profit is not None:
                text.append(
                    f"[tp={bbw_check_result.take_profit:.6f}]"
                )
            else:
                text.append(
                    "N/A",
                    style="dim",
                )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        if guard_result is not None:
            text.append("\nGUARD | ", style="cyan")

            if guard_result.allowed:
                text.append(
                    "CLOSE",
                    style="white on green",
                )
                text.append(" ALLOWED")
            else:
                text.append(
                    "CLOSE",
                    style="white on red",
                )
                text.append(
                    f" BLOCK({guard_result.reason})"
                )

        return text

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
        process_result: ProcessResult,
    ) -> ProcessResult:
        # Проверяем есть ли группа маленьких уровней для merge.
        # Если есть -> объединяем все уровни группы
        self.merge_levels.merge_multiple_levels()

        guard_result = self.is_exit_allowed()

        if not guard_result.allowed:
            process_result.executed = False
            process_result.status = self._get_status_line(
                guard_result=guard_result,
            )
            return process_result

        process_result, check_result, rearm_check_result, bbw_check_result = (
            self._resolve_action(
                process_result,
            )
        )
        process_result.status = self._get_status_line(
            check_result,
            rearm_check_result,
            bbw_check_result,
            guard_result,
        )

        return process_result
    
    def _execute_close(
        self,
        entry,
        process_result: ProcessResult,
        reason: str,
        source: ActionSource,
    ) -> ProcessResult:
        # Сигнал есть -> запускаем CLOSE
        action_command = ActionCommand(
                action=Action.CLOSE,
                symbol=self.symbol,
                levels=[entry],
                side=get_inverse_side(self.side),
                qty=entry.qty,
                reason=reason,
                source=source
            )
        process_result = self.action_service.process_action(
                action_command,
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
    ) -> tuple[ProcessResult, EntryCheckResult]:
        return self.entry_manager.resolve(
            process_result,
        )

    def _resolve_bbw_exit(
        self,
        process_result: ProcessResult,
    ) -> tuple[
        ProcessResult,
        RearmCheckResult | None,
        BBWCheckResult,
    ]:
        # Есть сигнал на выход?
        process_result.signal, entry, bbw_check_result = (
            self.partial_exit_bbw.check()
        )

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
                process_result, rearm_check_result = (
                    self.rearm_manager._resolve_rearm(
                        process_result,
                        initial_qty=entry.initial_qty
                    )
                )
                return (
                    process_result,
                    rearm_check_result,
                    bbw_check_result,
                )
            else:
                # CLOSE не выполнен -> выходим
                return process_result, None, bbw_check_result

        # Сигнала на выход нет
        return process_result, None, bbw_check_result

    def _resolve_action(
        self,
        process_result: ProcessResult,
    ) -> tuple[
        ProcessResult,
        EntryCheckResult | None,
        RearmCheckResult | None,
        BBWCheckResult,
    ]:
        # Выход по пересечению предыдущего уровня
        process_result = self._resolve_exit_cross(
            process_result,
        )
        if process_result.signal:
            return process_result, None, None, BBWCheckResult(
                has_position=False,
                take_profit=None,
            )

                
        # Выход по BBW
        process_result, rearm_check_result, bbw_check_result = (
            self._resolve_bbw_exit(
                process_result,
            )
        )
        if process_result.signal:
            return (
                process_result,
                None,
                rearm_check_result,
                bbw_check_result,
            )


        # Проверка на вход
        process_result, check_result = self._resolve_entry(
            process_result,
        )

        return (
            process_result,
            check_result,
            None,
            bbw_check_result,
        )    

    def _get_status_line(
        self,
        check_result: EntryCheckResult | None = None,
        rearm_check_result: RearmCheckResult | None = None,
        bbw_check_result: BBWCheckResult | None = None,
        guard_result: GuardResult | None = None,
    ):
        last_price = self.proxy_driver.get_last_price(self.symbol)
        status_line = self._build_status_line(
            price=last_price,
            check_result=check_result,
            rearm_check_result=rearm_check_result,
            bbw_check_result=bbw_check_result,
            guard_result=guard_result
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