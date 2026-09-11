from dataclasses import dataclass


@dataclass
class OptimizationResult:
    allowed: bool
    levels: list
    close_qty: float
    report: str

from enum import Enum

class CloseTiming(Enum):
    EARLY = "EARLY"
    TIMELY = "TIMELY"
    LATE = "LATE"    


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
        entries,
        profit_tolerance_ratio: float,
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
        timing = self._should_close_pair(
            pair=pair,
            last_price=work_price,
            profit_tolerance=profit_tolerance_ratio,
        )
        if timing != CloseTiming.TIMELY:
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

    def _is_in_profit_zone(
        self,
        breakeven: float,
        last_price: float,
        profit_tolerance: float,
    ) -> CloseTiming:

        if self.hedge_side == "Buy":
            # BUY: ниже зоны — EARLY, выше зоны — LATE
            band_low = breakeven
            band_high = breakeven * (
                1 + profit_tolerance
            )

            if last_price < band_low:
                return CloseTiming.EARLY

            if last_price > band_high:
                return CloseTiming.LATE

            return CloseTiming.TIMELY

        # SELL: выше зоны — EARLY, ниже зоны — LATE
        band_low = breakeven * (
            1 - profit_tolerance
        )
        band_high = breakeven

        if last_price > band_high:
            return CloseTiming.EARLY

        if last_price < band_low:
            return CloseTiming.LATE

        return CloseTiming.TIMELY

    
    def _should_close_pair(
        self,
        pair,
        last_price: float,
        profit_tolerance: float,
    ):
        prev_entry, next_entry = pair

        avg_entry = self._calc_avg_entry(
            prev_entry,
            next_entry,
        )

        breakeven = self._calc_breakeven_price(
            avg_entry,
        )

        return self._is_in_profit_zone(
            breakeven=breakeven,
            last_price=last_price,
            profit_tolerance=profit_tolerance,
        )