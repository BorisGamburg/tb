from action_processor.state.state import State
from action_processor.state.stack_schema import StackElem


class MergeLevels:
    def __init__(
        self,
        state_store: State,
        proxy_driver,
        symbol: str,
        side: str,
    ):
        self.state_store = state_store
        self.proxy_driver = proxy_driver
        self.symbol = symbol
        self.side = side

    def get_merge_threshold(self):
        # Получаем параметр из конфига
        merge_threshold_pct = self.state_store.data.merge_threshold_pct

        # Получаем баланс
        balance = self.proxy_driver.get_balance()

        # Получаем текущую цену
        cur_price = self.proxy_driver.get_last_price(self.symbol)

        # Получаем размер в usdt
        qty_in_usd = (
            float(merge_threshold_pct) / 100
        ) * balance

        # Получаем порог размера для уровней
        merge_threshold = qty_in_usd / cur_price

        return merge_threshold

    def __get_levels_to_merge(self, merge_threshold) -> list[StackElem]:
        # Получаем отсортированные уровни
        self.state_store.stack_mng.sort_stack(self.side)
        levels = self.state_store.stack_mng.data.entries

        # Ищем группу маленьких уровней
        small_levels = []
        total_qty = 0.0
        for level in levels:
            # Если размер уровня превышает порог -> обнуляем накопленные уровни и размер
            if level.qty >= merge_threshold:
                small_levels = []
                total_qty = 0.0
                continue

            # Размер уровня меньше порога -> запоминаем уровень и накапливаем размер
            small_levels.append(level)
            total_qty += level.qty

            # Если размер накоплен -> выходим
            if total_qty > merge_threshold:
                return small_levels

        # Подходящая группа не найдена -> выходим
        return []

    def merge_multiple_levels(self) -> None:
        # Получаем порог размера уровня
        merge_threshold = self.get_merge_threshold()

        # Ищем группу маленьких уровней
        levels_to_merge = self.__get_levels_to_merge(
            merge_threshold,
        )

        if not levels_to_merge:
            return

        # Объединяем найденные уровни
        self.state_store.stack_mng.merge_multiple_levels(
            levels_to_merge,
        )