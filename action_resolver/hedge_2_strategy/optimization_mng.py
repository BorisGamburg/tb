from dataclasses import dataclass
from enum import Enum


@dataclass
class Band:
    low: float
    high: float    

@dataclass
class OptimizationResult:
    allowed: bool
    levels: list
    close_qty: float
    report: str
    band: Band

class CloseProfitability(Enum):
    PROFIT = "PROFIT"
    BREAKEVEN = "BREAKEVEN"
    LOSS = "LOSS"

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
                band=Band(low=0.0, high=0.0),            
            )      

        # Проверяем, пора ли закрывать пару
        timing, band = self.should_close_pair(
            pair=pair,
            last_price=work_price,
            profit_tolerance=profit_tolerance_ratio,
        )
        if timing != CloseProfitability.BREAKEVEN:
            return OptimizationResult(
                allowed=False,
                levels=[],
                report=report,
                close_qty=0.0,
                band=Band(low=0.0, high=0.0,),            
            )        

        # Успешно прошли все проверки — оптимизация разрешена
        return OptimizationResult(
            allowed=True,
            levels=list(pair),
            close_qty=self._calc_close_qty(pair),
            report=report,
            band=band,        
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
    ) -> tuple[CloseProfitability, Band]:

        if self.hedge_side == "Buy":
            # BUY: ниже зоны — PROFIT, выше зоны — LOSS
            band = Band(
                low=breakeven,
                high=breakeven * (1 + profit_tolerance),
            )

            if last_price < band.low:
                return CloseProfitability.PROFIT, band

            if last_price > band.high:
                return CloseProfitability.LOSS, band

            return CloseProfitability.BREAKEVEN, band

        elif self.hedge_side == "Sell":
            # SELL: выше зоны — PROFIT, ниже зоны — LOSS
            band = Band(
                low=breakeven * (1 - profit_tolerance),
                high=breakeven,
            )

            if last_price > band.high:
                return CloseProfitability.PROFIT, band

            if last_price < band.low:
                return CloseProfitability.LOSS, band

            return CloseProfitability.BREAKEVEN, band

        raise ValueError(
            f"Unsupported hedge side: {self.hedge_side}"
        )
    
    def should_close_pair(
        self,
        pair,
        last_price: float,
        profit_tolerance: float,
    ) -> tuple[CloseProfitability, Band]:
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