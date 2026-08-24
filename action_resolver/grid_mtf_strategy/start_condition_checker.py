from typing import Optional
from action_processor.state.state import State
from action_resolver.grid_mtf_strategy.struct_detector import StructureDetector
from action_resolver.grid_mtf_strategy.ha_reversal import HAReversalSignal

class StartConditionChecker:
    def __init__(
        self,
        proxy_driver,
        state_store: State,
        symbol: str,
        side: str,
        runtime=None,
    ):
        self.proxy_driver = proxy_driver
        self.state_store = state_store
        self.symbol = symbol
        self.side = side
        self.runtime = runtime

        self.ha_signal = HAReversalSignal(
            proxy_driver=proxy_driver,
            symbol=symbol,
        )

        self.structure = StructureDetector(
            proxy_driver=proxy_driver,
            symbol=symbol
        )        

    def check(self) -> bool:
        cfg = self.state_store.data

        if not cfg.require_start_condition:
            return True

        tf = cfg.start_tf
        t = cfg.start_condition_type

        if t == "ha_reversal":
            rsi = self._get_rsi_last_closed(tf)
            start_rsi_threshold = cfg.start_rsi_threshold
            start_rsi_ok = self._is_rsi_entry_threshold_ok(rsi, start_rsi_threshold)

            # Лог по изменению
            tf_state = "PASS" if start_rsi_ok else "BLOCK"
            rsi_str = f"{rsi:.2f}" if rsi is not None else "N/A"
            th_str = f"{start_rsi_threshold:.0f}" if start_rsi_threshold is not None else "N/A"
            if self.runtime:
                self.runtime.rsi_entry_status = f"START_{tf_state} [{tf}m:({rsi_str}/{th_str})]"

            ha_ok, ha_message = self.ha_signal.is_entry(
                tf,
                self.side,
            )

            if self.runtime:
                self.runtime.ha_entry_status = ha_message

            return start_rsi_ok and ha_ok

        if t == "structure_break":
            return self.structure.is_entry(tf, self.side)

        raise RuntimeError(f"Unknown start_condition_type: {t}")

    def _get_rsi_last_closed(self, tf: str) -> Optional[float]:
        data = self.proxy_driver.get_rsi(
            symbol=self.symbol,
            tf=tf
        )
        return data.get("rsi_last_closed")

    def _is_rsi_entry_threshold_ok(self, rsi: Optional[float], threshold: Optional[float]) -> bool:
        if rsi is None or threshold is None:
            return False
        if self.side == "Sell":
            return rsi >= threshold
        return rsi <= threshold