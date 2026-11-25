from dataclasses import dataclass

from action_processor.state.state import State
from action_resolver.grid_mtf_strategy.ha_reversal import HAReversalSignal, HAReversResult
from action_resolver.grid_mtf_strategy.grid_mtf_map_mng import GridMTFMapMng
from services.bb_service import BBService


@dataclass
class DistanceCheckDetails:
    tf: str | None
    price: float | None
    last_entry_price: float | None
    bbw: float | None
    bbw_multiplier: float | None
    min_distance_ratio: float
    required_move: float | None
    threshold: float | None
    bb_upper: float | None = None
    bb_lower: float | None = None    

@dataclass
class DistanceCheckResult:
    ok: bool
    details: DistanceCheckDetails

@dataclass
class RsiCheckDetails:
    tf: str
    value: float | None
    threshold: float | None

@dataclass
class RsiCheckResult:
    ok: bool
    details: RsiCheckDetails

@dataclass
class EntryCheckResult:
    entry_allowed: bool
    ha_revers_result: HAReversResult
    rsi_check_result: RsiCheckResult
    distance_check_result: DistanceCheckResult

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
        return self._is_distance_ok(entries)

    def _check_ha_revers(self):
        # Получаем уровни
        entries = self.state_store.stack_mng.data.entries

        # Получаем тф для входа
        level = len(entries)
        tf = self.map_mng.get_tf_for_level(level)

        # Получаем текущую цену
        price = self.proxy_driver.get_last_price(
            self.symbol
        )

        # Проверяем пробой границы последней закрытой ha свечи
        return self.ha_signal.is_entry(tf, self.side, price)

    def _is_distance_ok(
        self,
        entries,
    ) -> DistanceCheckResult:
        # Если уровней нет -> выходим
        if not entries:
            distance_details = DistanceCheckDetails(
                tf=None,
                price=None,
                last_entry_price=None,
                bbw=None,
                bbw_multiplier=None,
                min_distance_ratio=0.0035,
                required_move=None,
                threshold=None,
            )

            return DistanceCheckResult(
                ok=True,
                details=distance_details,
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

        distance_bbw_tf = tpl.entry_dist_tf_bbw
        distance_bbw_multiplier = tpl.entry_dist_multiplier_bbw

        bb = self.bb_service.get_live(distance_bbw_tf)
        bbw = bb["width_abs"]
        #print(f"BBW DEBUG tf={distance_bbw_tf} up={bb['upper']:.6f} lo={bb['lower']:.6f} mid={bb['mid']:.6f} width={bbw:.6f}")


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

        distance_details = DistanceCheckDetails(
            tf=distance_bbw_tf,
            price=price,
            last_entry_price=last_entry.price,
            bbw=bbw,
            bbw_multiplier=distance_bbw_multiplier,
            min_distance_ratio=min_distance_ratio,
            required_move=required_move,
            threshold=distance_threshold,
            bb_upper=bb["upper"],
            bb_lower=bb["lower"],                
        )

        return DistanceCheckResult(
            ok=dist_ok,
            details=distance_details,
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

    def _check_rsi(self) -> RsiCheckResult:
        entries = self.state_store.stack_mng.data.entries
        level = len(entries)
        tpl = self.map_mng.get_template_by_level(level)

        rsi_tf = self._get_rsi_last_closed(
            tpl.entry_tf_ha_rsi
        )
        tf_threshold = tpl.entry_tf_threshold_rsi
        rsi_tf_entry_ok = self._is_rsi_entry_threshold_ok(
            rsi_tf,
            tf_threshold
        )

        rsi_check_details = RsiCheckDetails(
            tf=tpl.entry_tf_ha_rsi,
            value=rsi_tf,
            threshold=tf_threshold,
        )

        rsi_check_result = RsiCheckResult(
            ok=rsi_tf_entry_ok,
            details=rsi_check_details,
        )

        return rsi_check_result
        
    def check(self) -> EntryCheckResult:
        ha_revers_result = self._check_ha_revers()
        rsi_check_result = self._check_rsi()
        distance_check_result = self._check_distance()

        entry_allowed = (
            ha_revers_result.ok
            and rsi_check_result.ok
            and distance_check_result.ok
        )

        entry_check_result = EntryCheckResult(
            entry_allowed=entry_allowed,
            ha_revers_result=ha_revers_result,
            rsi_check_result=rsi_check_result,
            distance_check_result=distance_check_result,
        )

        return entry_check_result