from action_processor.action import (
    Action,
    ActionCommand,
)
from services.bb_service import BBService
from utils.utils import get_inverse_side


class PartialExitBBW:
    def __init__(
        self,
        runtime,
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
        self.runtime = runtime

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
        min_distance = (
            entry.price *
            self.state_store.data.min_profit_pct / 100
        )
        max_distance = (
            entry.price *
            self.state_store.data.max_profit_pct / 100
        )
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
            self.runtime.bbw_exit_status = "NO_POS"
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
            return None

        # Распаковываем контекст выхода
        prof_level, cur_price, cur_dist, min_dist, max_dist = exit_context

        # Проверяем, превысила ли текущая дистанция минимальную 
        # Если нет, то выходим без действий
        if cur_dist < min_dist:
            return None

        # Проверяем, превысила ли текущая дистанция максимальную
        # Если да, то даем команду на закрытие 
        if cur_dist >= max_dist:
            return self._exit(prof_level)

        # Проверяем, достигнут ли tp по BB
        if not self._is_bb_tp_reached(cur_price):
            return None

        return self._exit(prof_level)

    def check(self):
        # Получаем данные для проверки выхода
        exit_context = self._get_exit_context()

        # Проверка выхода 
        return self._check_exit(exit_context)

    def _exit(self, entry):
        self.runtime.pending_rearm = True

        return ActionCommand(
            action=Action.CLOSE,
            symbol=self.symbol,
            levels=[entry],
            side=get_inverse_side(self.side),
            qty=entry.qty,
            reason="bbw",
        )    

    def _update_exit_status(self, take_profit):
        self.runtime.bbw_exit_status = f"[tp={take_profit:.6f}]"    

    def _is_bb_tp_reached(self, cur_price):
        tp = self.get_bb_tp()
        self._update_exit_status(tp)

        if self.side == "Sell":
            return cur_price <= tp

        return cur_price >= tp        