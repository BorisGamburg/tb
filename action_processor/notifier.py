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
            qty_pct = None
            if hasattr(map_mng, 'templates_sorted') and level < len(map_mng.templates_sorted):
                template_name, map_elem = map_mng.templates_sorted[level]
                qty_pct = map_elem.qty_pct
            elif level >= len(map_mng.templates_sorted):
                template_name = "MAX_LEVEL"

            return (
                f"TEMPLATE: {template_name} | "
                f"TF: {tf} | "
                f"QTY PCT: {qty_pct}%"
            )

            
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

            for i, e in enumerate(sorted_entries):
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

    def log(self, message: str):
        self.logger.info(message)       

    def log_distance_blocked(self, runtime) -> None:
        """
        Логирует событие, когда сигналы HA и RSI готовы к входу, но дистанция блокирует ордер.
        Пишет в лог строго один раз при наступлении события.
        Состояние флага хранится внутри самой функции.
        """
        fn = Notifier.log_distance_blocked
        is_logged = getattr(fn, "_logged", False)

        ha_status = getattr(runtime, 'ha_entry_status', '')
        rsi_status = getattr(runtime, 'rsi_entry_status', '')
        dist_status = getattr(runtime, 'distance_entry_status', '')

        ha_plain = getattr(ha_status, 'plain', str(ha_status))
        rsi_plain = getattr(rsi_status, 'plain', str(rsi_status))

        ha_ok = 'PASS' in ha_plain
        rsi_ok = 'PASS' in rsi_plain
        dist_blocked = 'BLOCK' in str(dist_status)

        if ha_ok and rsi_ok and dist_blocked:
            if not is_logged:
                symbol = self.state_store.data.symbol
                side = self.state_store.data.side
                self.logger.info(
                    f"[ENTRY BLOCKED BY DISTANCE] Symbol: {symbol} | Side: {side} | "
                    f"HA: PASS | RSI: PASS | DIST: {dist_status}"
                )
                fn._logged = True
        else:
            fn._logged = False