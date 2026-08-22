from dataclasses import dataclass


@dataclass
class OptimizationResult:
    allowed: bool
    levels: list
    close_qty: float
    report: str


class OptimizationMng:

    def __init__(
        self,
        fee_taker: float,
        hedge_side: str,
    ):
        self.fee_taker = fee_taker
        self.hedge_side = hedge_side

    def _calc_avg_entry(
        self,
        prev_entry,
        next_entry,
    ) -> float:
        total_qty = (
            prev_entry.qty +
            next_entry.qty
        )

        if total_qty <= 0:
            raise Exception(
                f"Invalid pair qty: "
                f"prev={prev_entry.qty}, "
                f"next={next_entry.qty}"
            )

        return (
            prev_entry.price * prev_entry.qty +
            next_entry.price * next_entry.qty
        ) / total_qty    
    
    def _calc_breakeven_price(
        self,
        avg_entry: float,
    ) -> float:
        fee = self.fee_taker

        slippage = 0.003

        buffer_rate = (
            2 * fee +
            slippage
        )

        if self.hedge_side == "Buy":
            return avg_entry * (
                1 + buffer_rate
            )

        return avg_entry * (
            1 - buffer_rate
        )    
    
    def _find_pair(
        self,
        entries,
        last_price: float,
    ):
        report = ""

        # Сортируем стек по цене
        entries = sorted(
            entries,
            key=lambda e: e.price,
        )

        if len(entries) < 2:
            report += (
                f"Pair search: only {len(entries)} "
                f"level(s), pair not found.\n"
            )
            return None, report

        # Ищем пару, внутри которой находится цена
        for i in range(len(entries) - 1):
            prev_entry = entries[i]
            next_entry = entries[i + 1]

            if prev_entry.price <= last_price <= next_entry.price:

                if self.hedge_side == "Buy":
                    pair = (
                        prev_entry,
                        next_entry,
                    )
                else:
                    pair = (
                        next_entry,
                        prev_entry,
                    )

                report += (
                    "Pair search: "
                    f"{pair[0].price} -> "
                    f"{pair[1].price} "
                    f"(price={last_price})\n"
                )

                return pair, report

        report += (
            "Pair search: "
            f"price {last_price} "
            "outside stack.\n"
        )

        return None, report    
    
    def check(
        self,
        work_price: float,
        prev_work_price: float | None,
        entries,
        profit_tolerance_ratio: float,
        loss_tolerance_ratio: float,        
    ):
        report = ""

        # Ищем пару уровней, внутри которой находится текущая цена
        pair, msg = self._find_pair(
            entries,
            work_price,
        )
        report += msg
        if pair is None:
            return OptimizationResult(
                allowed=False,
                levels=[],
                report=report,
                close_qty=0.0,
            )      

        # Проверяем, пора ли закрывать пару
        ok, msg = self._should_close_pair(
            pair=pair,
            last_price=work_price,
            prev_price=prev_work_price,
            profit_tolerance=profit_tolerance_ratio,
            loss_tolerance=loss_tolerance_ratio,
        )
        report += msg
        if not ok:
            return OptimizationResult(
                allowed=False,
                levels=[],
                report=report,
                close_qty=0.0,
            )          

        # Успешно прошли все проверки — оптимизация разрешена
        return OptimizationResult(
            allowed=True,
            levels=list(pair),
            close_qty=self._calc_close_qty(pair),
            report=report,
        )    
    
    def _calc_close_qty(
        self,
        pair,
    ) -> float:
        prev_entry, next_entry = pair

        return (
            prev_entry.qty +
            next_entry.qty
        )    

    def _should_close_pair(
        self,
        pair,
        last_price: float,
        prev_price: float | None,
        profit_tolerance: float,
        loss_tolerance: float,
    ):
        report = ""

        if prev_price is None:
            report += "Close: previous price unavailable.\n"
            return False, report

        # Распаковываем пару
        prev_entry, next_entry = pair

        # Вычисляем среднюю цену пары
        avg_entry = self._calc_avg_entry(
            prev_entry,
            next_entry,
        )

        # Вычисляем безубыток
        breakeven = self._calc_breakeven_price(
            avg_entry,
        )

        # 1. Приоритет — прибыльная зона.
        if self._is_in_profit_zone(
            breakeven=breakeven,
            last_price=last_price,
            profit_tolerance=profit_tolerance,
        ):
            report += "Close: profit zone.\n"
            return (True, report)

        # 2. Проверяем пересечение BE в прибыльном направлении.
        crossed = self._is_breakeven_crossing(
            breakeven=breakeven,
            prev_price=prev_price,
            last_price=last_price,
        )
        if not crossed:
            report += "Close: no breakeven crossing.\n"
            return (False, report)

        # 3. Проверяем величину проскока.
        if self._is_acceptable_overshoot(
            breakeven=breakeven,
            last_price=last_price,
            loss_tolerance=loss_tolerance,
        ):
            report += "Close: acceptable overshoot.\n"
            return (True, report)

        report += "Close: overshoot too large.\n"
        return (False, report)
    
    def _is_in_profit_zone(
        self,
        breakeven: float,
        last_price: float,
        profit_tolerance: float,
    ) -> bool:

        if self.hedge_side == "Buy":
            return (
                breakeven <= last_price <= breakeven * (1 + profit_tolerance)
            )

        return (
            breakeven * (1 - profit_tolerance) <= last_price <= breakeven
        )

    
    def _is_breakeven_crossing(
        self,
        breakeven: float,
        prev_price: float,
        last_price: float,
    ) -> bool:

        if self.hedge_side == "Buy":
            return (
                prev_price > breakeven and
                last_price <= breakeven
            )

        return (
            prev_price < breakeven and
            last_price >= breakeven
        )    
    
    def _is_acceptable_overshoot(
        self,
        breakeven: float,
        last_price: float,
        loss_tolerance: float,
    ) -> bool:

        if self.hedge_side == "Buy":
            return (
                last_price >=
                breakeven * (1 - loss_tolerance)
            )

        return (
            last_price <=
            breakeven * (1 + loss_tolerance)
        )    