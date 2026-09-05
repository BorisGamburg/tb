from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_resolver.grid_mtf_strategy.grid_mtf_map_mng import GridMTFMapMng
from action_resolver.grid_mtf_strategy.start_condition_checker import StartConditionChecker
from action_processor.bootstrap import AppContext
from action_resolver.grid_mtf_strategy.partial_exit_cross import PartialExitCross
from action_resolver.grid_mtf_strategy.breakeven_checker import BreakevenChecker
from action_resolver.grid_mtf_strategy.entry_checker import EntryChecker
from action_resolver.grid_mtf_strategy.partial_exit_bbw import PartialExitBBW
from action_resolver.grid_mtf_strategy.profit_filter import ProfitFilter
from dataclasses import dataclass, field
from action_resolver.grid_mtf_strategy.rearm_checker import RearmChecker
from action_resolver.resolve_result import ResolveResult
from rich.text import Text
from common.trading_info import TradingInfo
from action_processor.action_guard import ActionGuard
from action_processor.action import Action, ActionCommand
from action_processor.action_service import ActionService


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

        # Инициализируем чекер условий старта
        self.start_condition_checker = StartConditionChecker(
            proxy_driver=self.proxy_driver,
            state_store=self.state_store,
            symbol=self.symbol,
            side=self.side,
            runtime=self.runtime,
        )    

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
            trading_info=self.trading_info
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

    def _resolve_action(self, status_line: Text, execution_result=None,) -> ResolveResult:
        # Выход по пересечению предыдущего уровня
        action = self.partial_exit_cross.check()
        if action:
            return ResolveResult(
                action_command=action,
                status=status_line,
            )

        # Выход по BBW
        action = self.partial_exit_bbw.check()
        if action:
            return ResolveResult(
                action_command=action,
                status=status_line,
            )

        # Проверка на rearm
        action = self.rearm_checker.check(execution_result)
        if action:
            return ResolveResult(
                action_command=action,
                status=status_line,
            )

        # Проверка на вход
        action = self.entry_checker.check()
        self.app_ctx.notifier.log_distance_blocked(self.runtime)
        if action:
            return ResolveResult(
                action_command=action,
                status=status_line,
            )

        return ResolveResult(
            action_command=None,
            status=status_line,
        )
    
    def _check_start_strategy(self, status_line: Text) -> ResolveResult | None:
        if self.state_store.data.require_start_condition and not self._started:
            if not self.start_condition_checker.check():
                return ResolveResult(
                    action_command=None,
                    status=status_line,
                )

            self._started = True
            self.logger.info("[START] condition satisfied → strategy armed")

        return None

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
            f"Require start condition: {data.require_start_condition}\n"
            f"Start condition type: {data.start_condition_type}\n"
            f"Start TF: {data.start_tf}\n"
            f"Start RSI threshold: {data.start_rsi_threshold}"
        )
        self.app_ctx.logger.info(params)

    def on_iteration(self) -> None:
        self.app_ctx.notifier.log(
            self.app_ctx.notifier.build_stack_report()
        )        

    def _handle_external_command(
        self,
        external_command,
    ) -> ResolveResult | None:

        if not external_command:
            return None

        command = external_command.get("command")

        if command == "CLOSE_POSITION":
            action_command = ActionCommand(
                action=Action.CLOSE_POSITION,
                symbol=self.symbol,
                side=self.state_store.data.side,
            )

            return ResolveResult(
                action_command=action_command,
                status="CLOSE_POSITION",
                skip_sleep=False,
            )

        if command == "TEST":
            print("TEST")
            return ResolveResult(
                action_command=None,
                status="TEST",
                skip_sleep=False,
            )

        return None        

    def is_exit_allowed(self) -> bool:
        """
        Проверяет, можно ли закрывать уровни сейчас.
        """
        if not self.state_store.data.exit_guard_enabled:
            self.runtime.guard_status = None
            return True

        return self.action_guard.is_allowed()

    def resolve(self, external_command, execution_result=None,) -> ResolveResult:
            external_result = self._handle_external_command(external_command)
            if external_result is not None:
                return external_result

            is_allowed = self.is_exit_allowed()
            status_line = self._get_status_line()

            if not is_allowed:
                return ResolveResult(
                    action_command=None,
                    status=status_line,
                )

            return self._resolve_action(status_line, execution_result,)

             