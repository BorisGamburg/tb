from .consume_action import ConsumeAction

class ConsumePlanner:

    def plan(
        self,
        levels,
        qty
    ) -> list[ConsumeAction]:

        actions = []

        remaining = qty

        # Идем по уровням по порядку
        # Порядок задается снаружи этой функции
        for lvl in levels:

            # Выходим, если больше отъедать нечего
            if remaining <= 0:
                break

            # Отъедаем от текущего уровня сколько возможно
            qty_before = lvl.qty
            qty_removed = min(qty_before, remaining)
            qty_after = qty_before - qty_removed

            # Запоминаем изменение уровня
            # Здесь уровень не меняем
            actions.append(
                ConsumeAction(
                    level=lvl,

                    qty_before=qty_before,
                    qty_removed=qty_removed,
                    qty_after=qty_after,

                    fully_removed=qty_after <= 0
                )
            )

            # Вычиляем сколько еще осталось отъесть
            remaining -= qty_removed

        return actions