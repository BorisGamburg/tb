from dataclasses import dataclass

from action_resolver.hedge_2_strategy.hedge_mode_selector import (
    HedgeModeSelector,
    HedgeMode,
)
from action_resolver.hedge_2_strategy.ha_trend_checker import (
    HATrendChecker,
)
from action_resolver.hedge_2_strategy.build_mng import (
    check_build,
    BuildResult,
)
from action_resolver.hedge_2_strategy.optimization_mng import (
    OptimizationMng,
)
from action_resolver.hedge_2_strategy.hedge_status import HedgeStatus
from action_resolver.hedge_2_strategy.position_info import (
    PositionInfo,
)

@dataclass
class HedgeContext:
    work_price: float
    bid: float
    ask: float
    prev_work_price: float | None
    hedge_position: PositionInfo
    main_position: PositionInfo
    main_unrealised_pnl: float
    entries: list
    trend_active: bool
    hedge_qty_ratio: float
    hedge_step_ratio: float
    profit_tolerance_ratio: float
    loss_tolerance_ratio: float

class HedgeModeMng:
    def __init__(
        self,
        app_ctx,
        state_store,
        trading_info,
    ):
        self.state_store = state_store
        self.proxy_driver = app_ctx.proxy_driver
        self.trading_info = trading_info
        self.symbol = state_store.data.symbol
        self.hedge_side = state_store.data.side
        self.main_side = "Sell" if self.hedge_side == "Buy" else "Buy"
        self.hedge_step_ratio = state_store.data.hedge_step_pct / 100
        self.profit_tolerance_ratio = state_store.data.profit_tolerance_pct / 100
        self.loss_tolerance_ratio = state_store.data.loss_tolerance_pct / 100
        self.hedge_qty_ratio = state_store.data.hedge_qty_pct / 100
        self.max_hedge_ratio = 0.5
        self.prev_work_price: float | None = None
        self.mode: HedgeMode | None = None
        self.trend_active: bool

        self.ha_trend = HATrendChecker(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
            side=self.hedge_side,
        )        

        self.optimization_manager = OptimizationMng(
            hedge_side=self.hedge_side,
            fee_taker=trading_info.fee_taker,
        )

        self.mode_selector = HedgeModeSelector(
            hedge_side=self.hedge_side,
            max_hedge_ratio=self.max_hedge_ratio,
        )

    def _load_context(self) -> HedgeContext:
        # Получаем рабочую цену:
        # Buy-хедж -> bid
        # Sell-хедж -> ask
        ticker = self.proxy_driver.get_ticker(self.symbol)

        if self.hedge_side == "Buy":
            work_price = float(ticker["bid"])
        else:
            work_price = float(ticker["ask"])        

        # Получаем данные по позициям
        hedge_position, main_position = self._get_positions_data()

        main_unrealised_pnl = self._calc_main_unrealised_pnl(
            ticker,
            main_position,
        )

        # Проверяем, активен ли тренд 
        self.trend_active = self.ha_trend.is_active(
            self.state_store.data.start_tf,
        )        

        # Формируем HedgeContext
        ctx = HedgeContext(
            work_price=work_price,
            bid=float(ticker["bid"]),
            ask=float(ticker["ask"]),
            prev_work_price=self.prev_work_price,
            hedge_position=hedge_position,
            main_position=main_position,
            main_unrealised_pnl=main_unrealised_pnl,
            entries=self.state_store.stack_mng.data.entries,
            trend_active=self.trend_active,
            hedge_qty_ratio=self.hedge_qty_ratio,
            hedge_step_ratio=self.hedge_step_ratio,
            profit_tolerance_ratio=self.profit_tolerance_ratio,
            loss_tolerance_ratio=self.loss_tolerance_ratio,
        ) 

        # Запоминаем предыдущую цену
        self.prev_work_price = work_price

        # Возвращаем контекст
        return ctx

    def check(self):
        # Собираем данные для бизнес-логики
        ctx = self._load_context()

        # Выполняем бизнес-логику
        return self._check_with_context(ctx)
    
    def _check_with_context(
        self,
        ctx: HedgeContext,
    ):
        # В зависимости от того, нужна защита или нет, выбираем режим работы
        mode, report, curr_ratio, required_ratio = (
            self.mode_selector.select_mode(
                unrealised_pnl=ctx.main_unrealised_pnl,
                main_pos_size=ctx.main_position.qty,
                hedge_pos_size=ctx.hedge_position.qty,
                entry_price=ctx.main_position.entry_price,
            )
        )
        self.mode = mode

        status = HedgeStatus(
            bid=ctx.bid,
            ask=ctx.ask,
            protection_current=curr_ratio,
            protection_required=required_ratio,
            pnl=ctx.main_unrealised_pnl,
            mode=mode,
            pairs=0,
        )

        # Если защита еще не набрана — проверяем, можно ли добавить следующий уровень
        if mode == HedgeMode.BUILD:
            build_result = check_build(
                trend_active=ctx.trend_active,
                work_price=ctx.work_price,
                entries=ctx.entries,
                hedge_step_ratio=ctx.hedge_step_ratio,
                main_pos_size=ctx.main_position.qty,
                hedge_pos_size=ctx.hedge_position.qty,
                hedge_qty_ratio=ctx.hedge_qty_ratio,
                hedge_side=self.hedge_side,
                trading_info=self.trading_info,
            )            
            build_result.report = report + build_result.report
            return build_result, status        

        # Если защита уже набрана — проверяем, можно ли выполнить оптимизацию
        if mode == HedgeMode.OPTIMIZATION:
            optimization_result = self.optimization_manager.check(
                work_price=ctx.work_price,
                prev_work_price=ctx.prev_work_price,
                entries=ctx.entries,
                profit_tolerance_ratio=ctx.profit_tolerance_ratio,
                loss_tolerance_ratio=ctx.loss_tolerance_ratio,
            )

            optimization_result.report = report + optimization_result.report
            return optimization_result, status               

        raise Exception(
            f"Unsupported hedge mode: {mode}"
        )

    def _get_positions_data(self):
        main_pos = self.proxy_driver.get_position(
            self.symbol,
            self.main_side,
        )

        hedge_pos = self.proxy_driver.get_position(
            self.symbol,
            self.hedge_side,
        )

        main_qty = float(main_pos["size"])

        if main_qty < 0:
            raise Exception(
                f"Invalid main position qty: {main_qty}"
            )

        hedge_position = PositionInfo(
            side=self.hedge_side,
            qty=float(hedge_pos["size"]),
            entry_price=float(hedge_pos["entry_price"]),
        )

        main_position = PositionInfo(
            side=self.main_side,
            qty=main_qty,
            entry_price=float(main_pos["entry_price"]),
        )

        return hedge_position, main_position

    def _calc_main_unrealised_pnl(
        self,
        ticker,
        main_position: PositionInfo,
    ) -> float:
        if self.main_side == "Buy":
            market_price = float(ticker["bid"])
            return (
                market_price - main_position.entry_price
            ) * main_position.qty

        market_price = float(ticker["ask"])
        return (
            main_position.entry_price - market_price
        ) * main_position.qty
        
