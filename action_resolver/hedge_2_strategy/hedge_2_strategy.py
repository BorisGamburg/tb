from decimal import Decimal

from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_processor.bootstrap import AppContext
from action_resolver.hedge_2_strategy.hedge_mode_mng import HedgeModeMng
from action_resolver.hedge_2_strategy.mode_to_action_transformer import transform
from action_resolver.hedge_2_strategy.hedge_status import HedgeStatus
from action_resolver.resolve_result import ResolveResult
from common.trading_info import TradingInfo
from action_processor.action import Action, ActionCommand
from signals.ha_reversal_signal import HAReversalSignal
from action_resolver.hedge_2_strategy.build_mng import calc_hedge_qty
from action_processor.action_service import ActionService
from action_processor.process_result import ProcessResult
from action_processor.execution.limit_order_result import LimitOrderStatus


class Hedge2Strategy(BaseStrategy):
    def __init__(
        self,
        state_store: State,
        app_ctx: AppContext,
        trading_info: TradingInfo,
    ) -> None:

        super().__init__()

        self.app_ctx = app_ctx
        self.state_store = state_store
        self.proxy_driver = app_ctx.proxy_driver

        self.symbol = state_store.data.symbol
        self.trading_info = trading_info

        self.hedge_mode_mng = HedgeModeMng(
            app_ctx=app_ctx,
            state_store=state_store,
            trading_info=trading_info,
        )

        self.ha_signal = HAReversalSignal(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
        )

        self.action_service = ActionService(
            app_ctx=app_ctx,
            state_store=state_store,
        )        

        self._log_parameters()

    def _build_status_line(
        self,
        status: HedgeStatus,
    ) -> str:
        protection_ok = status.protection_current >= status.protection_required
        protection_mark = "✓" if protection_ok else "✗"
        return (
            f"BID/ASK: {status.bid:.6f} — {status.ask:.6f} | "
            f"PROTECTION: cur={status.protection_current:.3f} | "
            f"req={status.protection_required:.3f} {protection_mark} | "            
            f"PNL: {status.pnl:+.6f} | "
            f"MODE: {status.mode.name} | "
            f"PAIRS: {status.pairs}"

        )


    def _log_parameters(self) -> None:
        self.app_ctx.logger.info(
            f"Symbol: {self.state_store.data.symbol} | "
            f"Side: {self.state_store.data.side}"
        )

    def _check_recovery(self) -> tuple[bool, ResolveResult]:
        empty_result = ResolveResult(
            action_command=ActionCommand(
                action=Action.NO_ACTION,
                symbol=self.symbol,
            ),
            status="",
            executed=False,
        )

        # Если recovery не нужен, то выходим
        if not self.state_store.data.recovery_enabled:
            return False, empty_result

        # Читаем параметры нужные для recovery
        rec_tf = self.state_store.data.recovery_timeframe
        side = self.state_store.data.side

        is_reversal, _ = self.ha_signal.is_entry(tf=rec_tf, side=side)
        if is_reversal:
            # Получаем размер уровня для recovery
            qty = self._calc_recovery_qty()
            if qty == 0.0:
                return False, empty_result

            # Отключаем recovery-флаг
            self.state_store.data.recovery_enabled = False
            self.state_store.save()

            # Формируем команду для открытия уровня
            action_command = ActionCommand(
                action=Action.OPEN,
                symbol=self.symbol,
                side=side,
                qty=qty,
                reason="recovery_reversal",
            )

            return True, ResolveResult(
                action_command=action_command,
                status=f"RECOVERY INITIATED on {rec_tf} | qty={qty}",
                executed=False
            )

        return False, empty_result

    def _calc_recovery_qty(self) -> float:
        side = self.state_store.data.side
        main_side = "Sell" if side == "Buy" else "Buy"

        main_pos = self.proxy_driver.get_position(self.symbol, main_side)
        main_qty = float(main_pos["size"])

        hedge_qty_ratio = self.state_store.data.hedge_qty_pct / 100
        return calc_hedge_qty(
            main_qty=main_qty,
            hedge_qty_ratio=hedge_qty_ratio,
            trading_info=self.trading_info,
        )

    def get_process_result(self, process_result, exec_result):
        process_result.action_command = exec_result.action_command
        process_result.price = exec_result.price
        process_result.qty = exec_result.qty
        process_result.fee = exec_result.fee
        process_result.executed = exec_result.executed

    def resolve(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        # 1. Проверяем одноразовый триггер Recovery
        recovery_triggered, recovery_result = self._check_recovery()
        if recovery_triggered:
            return self.action_service.process_action(
                recovery_result.action_command,
                process_result,
            )

        # Основная стратегия
        return self._check_mode_action(process_result)    

    def _check_mode_action(
        self,
        process_result: ProcessResult,
    ) -> ProcessResult:
        # Получаем режим
        mode_result, status = self.hedge_mode_mng.check()

        # Преобразуем режим в команду действия
        action_command = transform(
            mode_result,
            symbol=self.symbol,
            side=self.state_store.data.side,
        )

        # Формируем статусную строку
        status_line = self._build_status_line(status=status)

        if action_command.action == Action.NO_ACTION:
            process_result.status = status_line
            return process_result

        if action_command.action == Action.OPEN:
            process_result = self.action_service.process_action(
                action_command,
                process_result,
            )
            process_result.status = status_line
            return process_result

        if action_command.action == Action.CLOSE:
            return self._execute_close(
                action_command,
                process_result,
                status_line,
                status
            )

        raise ValueError(
            f"Unsupported action in Hedge2Strategy: {action_command.action}"
        )    

    def _execute_close(
        self,
        action_command: ActionCommand,
        process_result: ProcessResult,
        status_line: str,
        status: HedgeStatus,
    ) -> ProcessResult:
        exec_result = self.action_service.execution.execute(
            action_command,
        )
        self.get_process_result(process_result, exec_result)

        # Если действие не выполнено -> выходим
        if not exec_result.executed:
            process_result.status = status_line
            return process_result

        if exec_result.status == LimitOrderStatus.PARTIALLY_FILLED:
            return self._execute_close_partial(
                exec_result,
                process_result,
                status_line,
                status
            )

        if exec_result.status == LimitOrderStatus.FILLED:
            return self._execute_close_filled(
                exec_result,
                process_result,
                status_line,
                status
            )

        raise ValueError(
            f"Unexpected CLOSE execution status: {exec_result.status}"
        )

    def _execute_close_filled(
        self,
        exec_result,
        process_result: ProcessResult,
        status_line: str,
        status: HedgeStatus,
    ) -> ProcessResult:
        self._check_close_band(
            price=exec_result.price,
            status=status,
        )        

        self.action_service.accounting.apply(
            action=exec_result.action_command.action,
            price=exec_result.price,
            qty=exec_result.qty,
            fee=exec_result.fee,
            levels=exec_result.action_command.levels,
        )

        process_result.status = status_line
        return process_result        

    def calc_proportional_reductions(
        self,
        levels,
        executed_qty: float,
        qty_step: float,
        side: str,
    ):
        # Проверяем количество уровней
        if len(levels) != 2:
            raise ValueError(
                f"Expected exactly two levels, got {len(levels)}"
            )

        # Распаковываем уровни
        level_1, level_2 = levels

        # Определяем прибыльный уровень
        profitable_level = self._get_profitable_level(
            level_1,
            level_2,
            side,
        )

        # Вычисляем сумму размеров уровней
        total_qty = level_1.qty + level_2.qty

        # Вычисляем reduction для прибыльного уровня
        profitable_reduction = self._calc_profitable_reduction(
            executed_qty=executed_qty,
            profitable_qty=profitable_level.qty,
            total_qty=total_qty,
            qty_step=qty_step,
        )

        # Вычисляем reduction для убыточного уровня
        loss_reduction = self._calc_loss_reduction(
            executed_qty=executed_qty,
            profitable_reduction=profitable_reduction,
        )

        # Возвращаем reductions в правильном порядке
        if profitable_level is level_1:
            return profitable_reduction, loss_reduction

        return loss_reduction, profitable_reduction

    def _get_profitable_level(
        self,
        level_1,
        level_2,
        side: str,
    ):
        # Определяем прибыльный уровень
        if side == "Sell":
            return (
                level_1
                if level_1.price < level_2.price
                else level_2
            )

        if side == "Buy":
            return (
                level_1
                if level_1.price > level_2.price
                else level_2
            )

        raise ValueError(
            f"Unsupported side: {side}"
        )

    def _calc_profitable_reduction(
        self,
        executed_qty: float,
        profitable_qty: float,
        total_qty: float,
        qty_step: float,
    ):
        # Вычисляем математически точный reduction
        # для прибыльного уровня
        profitable_reduction_raw = (
            executed_qty * profitable_qty / total_qty
        )

        # Вычисляем округленный до шага инструмента reduction
        return self.ceil_to_step(
            profitable_reduction_raw,
            qty_step,
        )

    def _calc_loss_reduction(
        self,
        executed_qty: float,
        profitable_reduction: float,
    ):
        # Вычисляем reduction для убыточного уровня
        loss_reduction = executed_qty - profitable_reduction

        if loss_reduction < 0:
            raise ValueError(
                "Calculated loss reduction is negative: "
                f"{loss_reduction}"
            )

        return loss_reduction


    def ceil_to_step(self, value: float, step: float) -> float:
        value_decimal = Decimal(str(value))
        step_decimal = Decimal(str(step))

        lower = (
            value_decimal // step_decimal
        ) * step_decimal

        upper = lower + step_decimal

        if value_decimal == lower:
            return float(lower)

        return float(upper)    

    def _execute_close_partial(
        self,
        exec_result,
        process_result: ProcessResult,
        status_line: str,
        status: HedgeStatus,
    ) -> ProcessResult:
        self._check_close_band(
            price=exec_result.price,
            status=status,
        )

        levels = exec_result.action_command.levels
        executed_qty = exec_result.qty

        reductions = self.calc_proportional_reductions(
            levels=levels,
            executed_qty=executed_qty,
            qty_step=self.trading_info.qty_step,
            side=exec_result.action_command.side,
        )

        reduction_1, reduction_2 = reductions

        level_1, level_2 = levels

        new_qty_1 = level_1.qty - reduction_1
        new_qty_2 = level_2.qty - reduction_2

        if new_qty_1 < 0 or new_qty_2 < 0:
            raise ValueError(
                f"Partial close produced negative level qty | "
                f"new_qty_1={new_qty_1} | "
                f"new_qty_2={new_qty_2}"
            )        

        if new_qty_1 == 0:
            self.action_service.accounting.remove_level(level_1)
        else:
            self.action_service.accounting.update_level_qty(
                level_1,
                new_qty_1,
            )

        if new_qty_2 == 0:
            self.action_service.accounting.remove_level(level_2)
        else:
            self.action_service.accounting.update_level_qty(
                level_2,
                new_qty_2,
            )

        process_result.status = status_line
        return process_result    

    def _check_close_band(
        self,
        price: float,
        status: HedgeStatus,
    ) -> None:
        if price < status.band.low:
            raise ValueError(
                f"Close price below band | "
                f"price={price} | "
                f"band_low={status.band.low} | "
                f"band_high={status.band.high}"
            )

        if price > status.band.high:
            raise ValueError(
                f"Close price above band | "
                f"price={price} | "
                f"band_low={status.band.low} | "
                f"band_high={status.band.high}"
            )    