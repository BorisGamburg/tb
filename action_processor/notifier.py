from action_processor.execution.execution_result import ExecutionResult
from action_processor.state.state import State
from action_processor.action import Action, ActionCommand
import time


class Notifier:
    def __init__(
        self,
        logger,
        trade_logger,
        telegram,
        state_store: State,
    ):
        self.logger = logger
        self.trade_logger = trade_logger
        self.telegram = telegram
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
                    gross_pct = (entry_price - exit_price) / entry_price * 100 if entry_price else 0.0
                    gross_usd = (entry_price - exit_price) * qty
                else:
                    gross_pct = (exit_price - entry_price) / entry_price * 100 if entry_price else 0.0
                    gross_usd = (exit_price - entry_price) * qty

                fees = (entry_price * qty * fee_rate) + (exit_price * qty * fee_rate)
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

    def _build_message(
        self,
        result: ExecutionResult,
    ) -> str | None:
        """
        Формирует текст уведомления.
        """
        symbol = self.state_store.data.symbol
        side = self.state_store.data.side

        if result.action_command.action == Action.OPEN:
            return (
                "💎 LEVEL OPENED\n"
                f"Symbol: {symbol}\n"
                f"Side: {side}\n"
                f"Qty: {result.qty}\n"
                f"Price: {result.price}"
            )
        if result.action_command.action == Action.CLOSE:
            return (
                "📉 LEVELS CLOSED\n"
                f"Symbol: {symbol}\n"
                f"Qty: {result.qty}\n"
                f"Price: {result.price}"
            )

        return None

    def _get_current_tf_info(self) -> str:
        """Определяет активный темплейт и таймфрейм для текущего уровня стека."""
        map_mng = getattr(self.state_store, 'map_mng', None)
        stack = self.state_store.data.stack
        level = len(stack.entries) if stack and stack.entries else 0

        if not map_mng:
            return "MAP_MNG: N/A"

        try:
            # Получаем TF (используем тот же метод, что и в стратегии)
            tf = map_mng.get_tf_for_level(level)
            
            # Пытаемся достать имя темплейта
            template_name = "unknown"
            if hasattr(map_mng, 'templates_sorted') and level < len(map_mng.templates_sorted):
                template_name, _ = map_mng.templates_sorted[level]
            elif level >= len(map_mng.templates_sorted):
                template_name = "MAX_LEVEL"

            return f"TEMPLATE: {template_name} | TF: {tf}"
            
        except Exception as e:
            return f"TF_INFO: Error ({e})"       

    def build_stack_report(self) -> str:
        stack = self.state_store.data.stack
        level = len(stack.entries) if stack and stack.entries else 0

        tf_info = self._get_current_tf_info()

        lines = [
            tf_info,
            f"STACK SIZE: {level}"
        ]

        if level > 0:

            sorted_entries = sorted(
                stack.entries,
                key=lambda x: x.price,
                reverse=True,
            )

            visible_entries = sorted_entries[-10:]

            for i, e in enumerate(visible_entries):
                lines.append(
                    f"[{i:02d}] "
                    f"{e.price:>10.6f} | "
                    f"{e.qty:>8.2f}"
                )
        else:
            lines.append("STACK: empty")

        return "\n".join(lines)

    def log_iteration(self, iteration):
        self.logger.info("════════════════════════════════════════════════════════════")
        self.logger.info(f"Итерация {iteration}")

    def log_parameters(self) -> None:
        state = self.state_store.data
        log = self.logger.info

        log("════════════════════════════════════════════════════════════")
        log("ЗАГРУЖЕННЫЕ ПАРАМЕТРЫ")
        log(f"Symbol: {state.symbol} | Side: {state.side}")

        keys = [
            "hedge_step_pct",
            "hedge_qty_pct",
            "start_tf",
            "sleep_interval",
        ]

        for key in keys:
            if not hasattr(state, key):
                continue

            value = getattr(state, key)

            if isinstance(value, float) and "pct" in key:
                value = f"{value:.2f}%"

            log(f"{key}: {value}")

    def notify_action(self, act_cmd: ActionCommand) -> None:
        action = act_cmd.action.value.upper()
        reason = act_cmd.reason or "N/A"

        self.logger.info(
            f"[ACTION] {action} | reason={reason}"
        )    

    def notify_telegram(self, exec_result: ExecutionResult):
        tg_msg = self._build_message(exec_result)
        if tg_msg and self.telegram:
            self.telegram.send_telegram_message(tg_msg)        

    def log(self, message: str):
        self.logger.info(message)       

    def log_execution(self, exec_result: ExecutionResult):
        self.logger.info(
            f"[EXECUTION] action={exec_result.action_command.action.value} "
            f"| side={exec_result.action_command.side} "
            f"| qty={exec_result.qty} "
            f"| price={exec_result.price}"
        )             
