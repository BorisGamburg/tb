from dataclasses import dataclass

from services.bb_service import BBService


@dataclass
class BBWCheckResult:
    has_position: bool
    take_profit: float | None

class PartialExitBBW:
    def __init__(
        self,
        state_store,
        proxy_driver,
        price_service,
        map_mng,
        side,
        symbol,
    ):
        self.state_store = state_store
        self.proxy_driver = proxy_driver
        self.price_service = price_service
        self.map_mng = map_mng
        self.side = side
        self.symbol = symbol

        self.bb_service = BBService(
            proxy_driver=self.proxy_driver,
            symbol=self.symbol,
        )

    def get_prof_level_dist(self, price, entry):
        if self.side == "Sell":
            distance = entry.price - price
        else:
            distance = price - entry.price
            
        return distance
    
    def get_bb_tp(self):
        # Получаем tf для расчета take profit
        tf = self.get_tf()

        # Получаем BB для данного tf
        bb = self.bb_service.get_last_closed(tf)

        # Рассчитываем tp на основе BB
        tp = self._get_bb_tp(bb)

        return tp 

    def _get_bb_tp(self, bb):
        if self.side == "Sell":
            take_profit = (
                bb["mid"]
                - (bb["mid"] - bb["lower"]) * 1
            )
        else:
            take_profit = (
                bb["mid"]
                + (bb["upper"] - bb["mid"]) * 1
            )
        return take_profit

    def get_tf(self):
        entries = self.state_store.stack_mng.data.entries
        level_nr = len(entries) - 1
        tf = self.map_mng.get_tf_for_level(level_nr)
        return tf   

    def get_min_max_dist(self, entry):
        # Получаем мин дистанцию
        min_distance = (
            entry.price *
            self.state_store.data.min_profit_pct / 100
        )

        # Получаем макс дистанцию
        bb = self.bb_service.get_last_closed(self.get_tf())
        max_distance = (
            bb["width_abs"] *
            self.state_store.data.max_profit_bb_pct / 100
        )

        # Макс дистанция не должна быть меньше минимальной
        max_distance = max(min_distance, max_distance)
        
        return min_distance,max_distance

    def get_most_profitable_level(self, entries):
        if self.side == "Sell":
            entry = max(entries, key=lambda e: e.price)
        else:
            entry = min(entries, key=lambda e: e.price)
        return entry

    def _get_exit_context(self):
        # Получаем entries 
        entries = self.state_store.stack_mng.data.entries
        if not entries:
            return None

        # Получаем текущую цену
        cur_price = self.price_service.get_market_close_price(
            symbol=self.symbol,
            side=self.side,
        )

        # Получаем наиболее прибыльный уровень
        prof_level = self.get_most_profitable_level(entries)

        # Получаем дистанцию от наиболее прибыльного уровня до текущей цены 
        cur_dist = self.get_prof_level_dist(cur_price, prof_level)

        # Получаем min и max дистанции для выхода
        min_dist, max_dist = self.get_min_max_dist(prof_level)

        return prof_level, cur_price, cur_dist, min_dist, max_dist

    def _check_exit(self, exit_context):
        # Если контекст выхода не получен, то выходим без действий
        if exit_context is None:
            return False, None, None

        # Распаковываем контекст выхода
        prof_level, cur_price, cur_dist, min_dist, max_dist = exit_context

        # Проверяем, превысила ли текущая дистанция минимальную 
        # Если нет, то выходим без действий
        if cur_dist < min_dist:
            return False, None, None

        # Проверяем, превысила ли текущая дистанция максимальную
        # Если да, то даем команду на закрытие 
        if cur_dist >= max_dist:
            return True, prof_level, None
        # Проверяем, достигнут ли tp по BB
        reached, tp = self._is_bb_tp_reached(cur_price)
        if not reached:
            return False, None, tp

        return True, prof_level, tp

    def check(self):
        # Получаем данные для проверки выхода
        exit_context = self._get_exit_context()

        if exit_context is None:
            return (
                False,
                None,
                BBWCheckResult(
                    has_position=False,
                    take_profit=None,
                ),
            )

        # Проверка выхода
        signal, entry, tp = self._check_exit(exit_context)

        return (
            signal,
            entry,
            BBWCheckResult(
                has_position=True,
                take_profit=tp,
            ),
        )

    def _is_bb_tp_reached(self, cur_price):
        tp = self.get_bb_tp()

        if self.side == "Sell":
            reached = cur_price <= tp
        else:
            reached = cur_price >= tp

        return reached, tp 