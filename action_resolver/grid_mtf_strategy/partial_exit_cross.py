from dataclasses import dataclass

from action_processor.state.state import State
from common.market_service import MarketService
from action_resolver.grid_mtf_strategy.breakeven_checker import BreakevenChecker
from action_processor.state.stack_schema import StackElem


@dataclass
class CrossCheckDetails:
    price: float | None
    most_profitable_price: float | None
    previous_price: float | None
    cross_ok: bool
    breakeven_ok: bool

class PartialExitCross:
    def __init__(
        self,
        state_store: State,
        price_service: MarketService,
        side: str,
        symbol: str,
        breakeven_checker: BreakevenChecker,
    ):
        self.state_store = state_store
        self.price_service = price_service
        self.side = side
        self.symbol = symbol
        self.breakeven_checker = breakeven_checker

    def _evaluate_cross_condition(self, sorted_entries, price):
        if self.side == "Buy":
            most_profitable_level = sorted_entries[0]
            prev = sorted_entries[1]
            cond = price >= prev.price
        else:
            most_profitable_level = sorted_entries[-1]
            prev = sorted_entries[-2]
            cond = price <= prev.price

        return most_profitable_level, prev, cond

    def check(self) -> tuple[bool, StackElem | None, CrossCheckDetails]:
        entries = self.state_store.stack_mng.data.entries

        # Если у нас меньше 2 уровней, то сразу выходим
        if len(entries) < 2:
            cross_check_details = CrossCheckDetails(
                price=None,
                most_profitable_price=None,
                previous_price=None,
                cross_ok=False,
                breakeven_ok=False,
            )            
            return False, None, cross_check_details

        # Сортируем уровни по цене по возрастанию
        sorted_entries = sorted(entries, key=lambda x: x.price)

        # Получаем текущую цену инструмента
        market_close_price = self.price_service.get_market_close_price(
            symbol=self.symbol,
            side=self.side,
        )

        # Определяем самый прибыльный и предыдущий уровни в зависимости от стороны позиции
        # и находится ли текущая цена выше/ниже предыдущего уровня
        most_profitable_level, prev, cond = self._evaluate_cross_condition(sorted_entries, market_close_price)
        cross_check_details = CrossCheckDetails(
            price=market_close_price,
            most_profitable_price=most_profitable_level.price,
            previous_price=prev.price,
            cross_ok=cond,
            breakeven_ok=False,
        )

        if not cond:
            return False, None, cross_check_details

        # Не даем закрывать уровень, если он не прошел проверку на безубыток
        breakeven_ok = self.breakeven_checker.is_ok(
            entry=most_profitable_level,
            price=market_close_price,
        )
        cross_check_details.breakeven_ok = breakeven_ok
        if not breakeven_ok:
            return False, None, cross_check_details

        # Возвращаем команду на закрытие уровня
        return True, most_profitable_level, cross_check_details