from dataclasses import dataclass

from action_processor.state.state import State
from action_resolver.grid_mtf_strategy.ha_reversal import HAReversalSignal, HAReversalResult
from action_resolver.grid_mtf_strategy.grid_mtf_map_mng import GridMTFMapMng
from services.bb_service import BBService

@dataclass
class DistanceCheckResult:
    ok: bool
    threshold: float | None

@dataclass
class RsiCheckResult:
    ok: bool
    value: float | None
    threshold: float | None
    tf: str    

@dataclass
class BbCheckResult:
    ok: bool
    value: float | None
    mid: float | None
    tf: str

@dataclass
class EntryCheckResult:
    entry_allowed: bool
    ha: HAReversalResult
    rsi: RsiCheckResult
    bb: BbCheckResult
    distance: DistanceCheckResult

class EntryChecker:
    def __init__(
        self,
        state_store: State,
        map_mng: GridMTFMapMng,
        proxy_driver,
        price_service,
        symbol: str,
        side: str,
    ):
        self.state_store = state_store
        self.map_mng = map_mng
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.symbol = symbol
        self.side = side

        self.ha_signal = HAReversalSignal(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
        )

        self.bb_service = BBService(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
        )        

    def _get_rsi_last_closed(self, tf):

        data = self.proxy_driver.get_rsi(
            symbol=self.symbol,
            tf=tf
        )

        return data.get("rsi_last_closed")

    def _is_rsi_entry_threshold_ok(
        self,
        rsi,
        threshold
    ) -> bool:

        if rsi is None or threshold is None:
            return False

        if self.side == "Sell":
            return rsi >= threshold

        return rsi <= threshold

    def _check_distance(self) -> DistanceCheckResult:
        # Получаем уровни
        entries = self.state_store.stack_mng.data.entries

        # Проверяем дистанцию
        distance_result = self._is_distance_ok(entries)

        return distance_result

    def _check_ha_revers(self):
        # Получаем уровни
        entries = self.state_store.stack_mng.data.entries

        # Получаем тф для входа
        level = len(entries)
        tf = self.map_mng.get_tf_for_level(level)

        # Проверяем разворот по ha
        result = self.ha_signal.is_entry(tf, self.side)
        return result

    def _is_distance_ok(
        self,
        entries,
    ) -> DistanceCheckResult:
        # Если уровней нет -> выходим
        if not entries:
            return DistanceCheckResult(
                ok=True,
                threshold=None,
            )

        # Получаем текущую цену
        price = self.proxy_driver.get_last_price(
            self.symbol
        )

        # Берем наименее убыточный уровень
        last_entry = entries[-1]

        # Получаем тф из текущего map
        # Получаем параметры из текущего template
        level = len(entries)
        tpl = self.map_mng.get_template_by_level(level)

        distance_bbw_tf = tpl.distance_bbw_tf
        distance_bbw_multiplier = tpl.distance_bbw_multiplier

        bb = self.bb_service.get_live(distance_bbw_tf)
        bbw = bb["width_abs"]


        min_distance_ratio = 0.0035

        required_move = max(
            distance_bbw_multiplier * bbw,
            min_distance_ratio * price
        )

        if self.side == "Sell":
            distance_threshold = last_entry.price + required_move
            dist_ok = price > distance_threshold
        else:
            distance_threshold = last_entry.price - required_move
            dist_ok = price < distance_threshold

        return DistanceCheckResult(
            ok=dist_ok,
            threshold=distance_threshold,
        )

    def _get_last_atr(
        self,
        tf: str,
        period: int = 14
    ) -> float:

        response = self.proxy_driver.get_atr_ohlc(
            symbol=self.symbol,
            tf=tf,
            length=period
        )

        if "error" in response:
            raise RuntimeError(response["error"])

        atr_values = response.get("atr")

        if not atr_values or len(atr_values) < 2:
            raise RuntimeError("ATR data invalid")

        atr = atr_values[-2]

        if atr is None or atr <= 0:
            raise RuntimeError(
                f"Invalid ATR: {atr}"
            )

        return atr

    def _check_bb(self) -> BbCheckResult:
        # Получаем среднюю Боллингера
        bb_mid, bb_tf = self.get_bb_mid()

        # Получаем тек цену
        cur_price = self.proxy_driver.get_last_price(
            self.symbol
        )

        # Сравниваем тек цену со средней Боллингера
        bb_entry_ok = self.get_bb_entry_ok(bb_mid, cur_price)

        return BbCheckResult(
            ok=bb_entry_ok,
            value=cur_price,
            mid=bb_mid,
            tf=bb_tf,
        )
        
    def get_bb_entry_ok(self, bb_mid, cur_price):
        if self.side == "Sell":
            bb_entry_ok = cur_price > bb_mid
        else:
            bb_entry_ok = cur_price < bb_mid
        return bb_entry_ok

    def get_bb_mid(self):
        entries = self.state_store.stack_mng.data.entries
        level = len(entries)
        tpl = self.map_mng.get_template_by_level(level)
        bb = self.bb_service.get_live(tpl.htf_filter)
        bb_mid = bb["mid"]
        return bb_mid, tpl.htf_filter
    
    def _check_rsi(self) -> RsiCheckResult:
        entries = self.state_store.stack_mng.data.entries
        level = len(entries)
        tpl = self.map_mng.get_template_by_level(level)

        rsi_tf = self._get_rsi_last_closed(
            tpl.tf_filter
        )
        tf_threshold = tpl.tf_rsi_entry_threshold
        rsi_tf_entry_ok = self._is_rsi_entry_threshold_ok(
            rsi_tf,
            tf_threshold
        )

        return RsiCheckResult(
            ok=rsi_tf_entry_ok,
            value=rsi_tf,
            threshold=tf_threshold,
            tf=tpl.tf_filter,
        )
        
    def check(self) -> EntryCheckResult:
        ha_result = self._check_ha_revers()
        rsi_result = self._check_rsi()
        bb_result = self._check_bb()
        distance_result = self._check_distance()

        entry_allowed = (
            ha_result.signal
            and rsi_result.ok
            and bb_result.ok
            and distance_result.ok
        )

        return EntryCheckResult(
            entry_allowed=entry_allowed,
            ha=ha_result,
            rsi=rsi_result,
            bb=bb_result,
            distance=distance_result,
        )