from action_processor.execution.execution_result import ExecutionResult
from action_processor.state.state import State
from action_processor.action import Action
import time


class TradeTableLogger:

    def __init__(
        self,
        trade_logger,
        state_store: State,
    ):
        self.trade_logger = trade_logger
        self.state_store = state_store

    def log_trade_table(self, exec_result: ExecutionResult):
        symbol = self.state_store.data.symbol
        side = self.state_store.data.side
        fee_rate = getattr(self.state_store.data, 'fee_taker', 0.0002)
        timestamp = time.strftime("%d.%m %H:%M:%S")

        if exec_result.action_command.action == Action.OPEN:
            qty = exec_result.qty or 0.0
            price = exec_result.price or 0.0
            reason = exec_result.action_command.reason or "N/A"
            level = len(self.state_store.stack_mng.data.entries)
            val_usd = price * qty
            fee = val_usd * fee_rate

            msg = (
                f"{timestamp:<16} | 🟢OPEN| {symbol:<12} | {side:<4} | #{level:02d} | "
                f"{qty:<7.1f} | {price:<10.6f} | -          | -             | -       | "
                f"-{fee:<9.6f} | -            | -      | {reason}"
            )
            self.trade_logger.info(msg)

        elif exec_result.action_command.action == Action.CLOSE:
            reason = exec_result.action_command.reason or "N/A"
            levels = exec_result.action_command.levels or []

            for level_obj in levels:
                qty = level_obj.qty
                entry_price = level_obj.price
                exit_price = exec_result.price or 0.0

                if side == "Sell":
                    gross_pct = (
                        (entry_price - exit_price) / entry_price * 100
                        if entry_price else 0.0
                    )
                    gross_usd = (entry_price - exit_price) * qty
                else:
                    gross_pct = (
                        (exit_price - entry_price) / entry_price * 100
                        if entry_price else 0.0
                    )
                    gross_usd = (exit_price - entry_price) * qty

                fees = (
                    (entry_price * qty * fee_rate)
                    + (exit_price * qty * fee_rate)
                )
                net_usd = gross_usd - fees
                net_pct = gross_pct - (2 * fee_rate * 100)

                level_idx = getattr(level_obj, 'level_index', 1)

                msg = (
                    f"{timestamp:<16} | 🔴CLOS| {symbol:<12} | {side:<4} | #{level_idx:02d} | "
                    f"{qty:<7.1f} | {exit_price:<10.6f} | {entry_price:<10.6f} | "
                    f"+{gross_usd:<12.6f} | +{gross_pct:<6.2f}% | -{fees:<9.6f} | "
                    f"+{net_usd:<11.6f} | +{net_pct:<5.2f}% | {reason}"
                )
                self.trade_logger.info(msg)