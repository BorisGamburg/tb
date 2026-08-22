from prog.action_resolver.base_strategy import BaseStrategy
from prog.action_processor.state.state import State
from prog.action_processor.bootstrap import AppContext
from prog.action_resolver.hedge_2_strategy.hedge_mode_mng import HedgeModeMng
from prog.action_resolver.hedge_2_strategy.mode_to_action_transformer import transform
from prog.action_resolver.resolve_result import ResolveResult
from prog.common.trading_info import TradingInfo


class Hedge2Strategy(BaseStrategy):
    def __init__(
        self,
        state_store: State,
        app_ctx: AppContext,
        trading_info: TradingInfo,
    ) -> None:       

        super().__init__()
        
        self.state_store = state_store
        self.proxy_driver = app_ctx.proxy_driver

        self.symbol = state_store.data.symbol

        self.hedge_mode_mng = HedgeModeMng(
            app_ctx=app_ctx,
            state_store=state_store,
            trading_info=trading_info,
        )

    def resolve(self, ctx) -> ResolveResult:
        # Получаем режим 
        mode_result = self.hedge_mode_mng.check()
        report = mode_result.report

        # Преобразуем режим в команду действия
        action_command = transform(
            mode_result,
            symbol=self.symbol,
            side=self.state_store.data.side,
        )

        # Формируем статусную строку 
        status_line = self._build_status_line(report=report)

        # Возвращаем результат разрешения
        return ResolveResult(
            action_command=action_command,
            status=status_line,
            skip_sleep=False,
        )    

    def _build_status_line(
        self,
        report: str
    ) -> str:
        last_price = self.proxy_driver.get_last_price(self.symbol)
        return (
            f"Price: {last_price:.6f} "
            f"{report}"
        )
