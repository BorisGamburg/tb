from dataclasses import dataclass

from action_resolver.hedge_3_strategy.hedge_mode_selector import (
    HedgeProtectCheck,
    HedgeMode,
)
from common.ha_trend_checker import HATrendChecker
from action_resolver.hedge_3_strategy.build_mng import (
    calc_hedge_qty,
    check_build,
    BuildResult,
)
from action_resolver.hedge_3_strategy.hedge_regulator import (
    RegAction,
    decide,
)
from action_resolver.hedge_3_strategy.hedge_unwind import (
    HoldResult,
    UnwindResult,
    find_unwind_qty,
    SCHEME_B_MIN_PNL,
    SCHEME_B_MIN_STACK_PCT,
    SCHEME_B_PROFIT_ORDER,
    SCHEME_B_TARGET_PCT,
    SCHEME_B_TRIGGER_PCT,
)
from action_resolver.hedge_3_strategy.hedge_status import HedgeStatus
from action_resolver.hedge_3_strategy.position_info import (
    PositionInfo,
)
from action_processor.bootstrap import AppContext
from common.unwind.unwind_advisor import UnwindAdvisor, UnwindConfig



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
        app_ctx: AppContext,
        state_store,
        trading_info,
        unwinder,
    ):
        self.unwinder = unwinder
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
        self.trend_active: bool

        self.ha_trend = HATrendChecker(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
            side=self.hedge_side,
        )        

        self.unwind_advisor = UnwindAdvisor(
            proxy_driver=self.proxy_driver,
            trading_info=trading_info,
        )

        self.protect_check = HedgeProtectCheck(
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
        # Схема A: основная позиция есть и не в плюсе.
        # Иначе (основная в плюсе или её нет) - схема B (хвосты, как в
        # пирамиде 2); пока не реализована, ничего не делаем.
        if ctx.main_position.qty > 0 and ctx.main_unrealised_pnl <= 0:
            return self._check_scheme_a(ctx)
        return self._check_scheme_b(ctx)

    def _check_scheme_a(self, ctx: HedgeContext):
        main_qty = ctx.main_position.qty
        hedge_qty = ctx.hedge_position.qty

        cur_ratio, req_ratio = self.protect_check.get_ratios(
            unrealised_pnl=ctx.main_unrealised_pnl,
            main_qty=main_qty,
            hedge_qty=hedge_qty,
            entry_price=ctx.main_position.entry_price,
        )

        # Шаг регулятора: один хедж-уровень (hedge_qty_pct от основной)
        step_qty = calc_hedge_qty(
            main_qty=main_qty,
            hedge_qty_ratio=ctx.hedge_qty_ratio,
            trading_info=self.trading_info,
        )
        decision = decide(main_qty, hedge_qty, req_ratio, step_qty)

        unwind_wait = False
        if decision.action == RegAction.BUILD:
            mode = HedgeMode.BUILD
            result = check_build(
                trend_active=ctx.trend_active,
                work_price=ctx.work_price,
                entries=ctx.entries,
                hedge_step_ratio=ctx.hedge_step_ratio,
                main_pos_size=main_qty,
                hedge_pos_size=hedge_qty,
                hedge_qty_ratio=ctx.hedge_qty_ratio,
                hedge_side=self.hedge_side,
                trading_info=self.trading_info,
            )
        elif decision.action == RegAction.UNWIND:
            mode = HedgeMode.UNWIND
            result = find_unwind_qty(
                unwinder=self.unwinder,
                levels=ctx.entries,
                side=self.hedge_side,
                steps=decision.steps,
                step_qty=decision.step_qty,
                price=ctx.work_price,
            )
            unwind_wait = result.wait
        else:
            mode = HedgeMode.HOLD
            result = HoldResult()

        status = HedgeStatus(
            bid=ctx.bid,
            ask=ctx.ask,
            protection_current=cur_ratio,
            protection_required=req_ratio,
            pnl=ctx.main_unrealised_pnl,
            mode=mode,
            zone_low=decision.zone_low,
            zone_high=decision.zone_high,
            unwind_wait=unwind_wait,
            scheme="A",
        )
        return result, status

    def _check_scheme_b(self, ctx: HedgeContext):
        """Схема B: основная позиция в плюсе или её нет. Хвосты хеджа
        сворачиваем по L/P тем же советчиком, что и в пирамиде 2."""
        main_qty = ctx.main_position.qty
        cur_ratio = ctx.hedge_position.qty / main_qty if main_qty > 0 else 0.0

        config = UnwindConfig(
            symbol=self.symbol,
            side=self.hedge_side,
            trigger_pct=SCHEME_B_TRIGGER_PCT,
            target_pct=SCHEME_B_TARGET_PCT,
            min_pnl=SCHEME_B_MIN_PNL,
            min_stack_pct=SCHEME_B_MIN_STACK_PCT,
        )
        report = self.unwind_advisor.check(config, ctx.entries)

        if report is not None and report.qty_to_close > 0:
            mode = HedgeMode.UNWIND
            result = UnwindResult(
                found=True,
                qty=report.qty_to_close,
                price=report.price,
                steps=0,
                wait=False,
                min_pnl=SCHEME_B_MIN_PNL,
                profit_order=SCHEME_B_PROFIT_ORDER,
            )
        else:
            mode = HedgeMode.HOLD
            result = HoldResult()

        status = HedgeStatus(
            bid=ctx.bid,
            ask=ctx.ask,
            protection_current=cur_ratio,
            protection_required=0.0,
            pnl=ctx.main_unrealised_pnl,
            mode=mode,
            scheme="B",
            scheme_info=self._format_scheme_b(report),
        )
        return result, status

    @staticmethod
    def _format_scheme_b(report) -> str:
        if report is None:
            return "STACK: empty"
        plan = report.plan
        ratio = "∞" if plan.ratio == float("inf") else f"{plan.ratio * 100:.1f}%"
        trigger = f"{SCHEME_B_TRIGGER_PCT:g}%"
        if report.stack_pct < SCHEME_B_MIN_STACK_PCT:
            return (
                f"STACK {report.stack_pct:.1f}% < "
                f"{SCHEME_B_MIN_STACK_PCT:g}% | L/P {ratio}"
            )
        if not plan.triggered:
            return f"L/P {ratio} ≤ {trigger} | L {plan.L:.4f} P {plan.P:.4f}"
        if not plan.pieces:
            return f"L/P {ratio} > {trigger} | donors don't cover"
        return f"L/P {ratio} > {trigger} | CLOSE {plan.total_qty:g}"

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
