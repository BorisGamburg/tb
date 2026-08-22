from rich.text import Text
from prog.action_processor.action import (Action, ActionCommand)
from prog.action_resolver.grid_mtf_strategy.profit_filter import ProfitFilter
from prog.action_resolver.grid_mtf_strategy.ha_reversal import HAReversalSignal
from prog.utils.utils import get_inverse_side


class HAExit:
    def __init__(
        self,
        runtime,
        state_store,
        map_mng,
        proxy_driver,
        price_service,
        symbol,
        side,
        fee_taker
    ):
        self.runtime = runtime        
        self.state_store = state_store
        self.map_mng = map_mng
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.symbol = symbol
        self.side = side

        self.profit_filter = ProfitFilter(
            price_service=self.price_service,
            symbol=self.symbol,
            side=self.side,
            fee_taker=fee_taker
        )     

        self.ha_signal = HAReversalSignal(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
        )           

    def _is_rsi_exit_threshold_ok(
        self,
        rsi,
        threshold,
    ) -> bool:

        if rsi is None or threshold is None:
            return False

        if self.side == "Sell":
            return rsi <= threshold

        return rsi >= threshold    
    
    def _get_rsi_last_closed(
        self,
        tf,
    ):

        data = self.proxy_driver.get_rsi(
            symbol=self.symbol,
            tf=tf
        )

        return data.get(
            "rsi_last_closed"
        )   

    def _is_rsi_exit_ok(self) -> bool:
        # Получаем все уровни из стека
        entries = self.state_store.stack_mng.data.entries
        level = len(entries) - 1
        if level < 0:
            return False

        # Получаем template для текущего уровня
        template = self.map_mng.get_template_by_level(level)

        # --- TF RSI ---
        rsi_tf = self._get_rsi_last_closed(
            template.tf_filter
        )
        tf_threshold = template.tf_rsi_exit_threshold
        rsi_tf_exit_ok = self._is_rsi_exit_threshold_ok(
            rsi_tf,
            tf_threshold
        )

        # --- HTF RSI ---
        rsi_htf = self._get_rsi_last_closed(
            template.htf_filter
        )
        htf_threshold = template.htf_rsi_exit_threshold
        rsi_htf_exit_ok = self._is_rsi_exit_threshold_ok(
            rsi_htf,
            htf_threshold
        )

        overall = (
            "PASS"
            if rsi_tf_exit_ok and rsi_htf_exit_ok
            else "BLOCK"
        )

        tf_v = (
            f"{rsi_tf:.1f}"
            if rsi_tf is not None
            else "N/A"
        )
        htf_v = (
            f"{rsi_htf:.1f}"
            if rsi_htf is not None
            else "N/A"
        )

        tf_th = (
            f"{tf_threshold:.0f}"
            if tf_threshold is not None
            else "N/A"
        )
        htf_th = (
            f"{htf_threshold:.0f}"
            if htf_threshold is not None
            else "N/A"
        )

        tf_s = "PASS" if rsi_tf_exit_ok else "BLOCK"
        htf_s = "PASS" if rsi_htf_exit_ok else "BLOCK"

        status = Text()
        status.append(
            overall,
            style="black on green" if overall == "PASS" else "white on red",
        )
        status.append(f" [{template.tf_filter}m:")
        status.append(
            tf_s,
            style="black on green" if tf_s == "PASS" else "white on red",
        )
        status.append(f"({tf_v}/{tf_th}) | {template.htf_filter}m:")
        status.append(
            htf_s,
            style="black on green" if htf_s == "PASS" else "white on red",
        )
        status.append(f"({htf_v}/{htf_th})]")

        self.runtime.rsi_exit_status = status

        return rsi_tf_exit_ok and rsi_htf_exit_ok     

    def check(self):
        entries = self.state_store.stack_mng.data.entries

        if not entries:
            self.runtime.rsi_exit_status = Text(
                "NO_POS",
                style="yellow",
            )
            return None

        # Проверяем все фильтры независимо
        rsi_ok = self._is_rsi_exit_ok()
        ha_ok = self._is_ha_exit_signal()

        # Решение принимаем только после всех проверок
        if not rsi_ok or not ha_ok:
            return None

        # Проверяем прибыльные уровни
        level = self.profit_filter.get_most_profitable_level(entries)
        if level is None:
            return None

        self.runtime.pending_rearm = True

        return ActionCommand(
            action=Action.CLOSE,
            symbol=self.symbol,
            levels=[level],
            side=get_inverse_side(self.side),
            qty=level.qty,
            reason="ha_exit",
        )

    def _is_ha_exit_signal(self) -> bool:
        entries = self.state_store.stack_mng.data.entries

        level_number = len(entries) - 1
        tf = self.map_mng.get_tf_for_level(level_number)

        is_exit, message = self.ha_signal.is_exit(
            tf,
            self.side,
        )

        self.runtime.ha_exit_status = message

        return is_exit