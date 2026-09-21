from action_processor.state.stack_schema import StackElem
from action_resolver.hedge_2_strategy.close_result_calculator import (
    CloseResultCalculator,
)


class AlternativeSearchService:
    def __init__(
        self,
        close_result_calculator: CloseResultCalculator,
        hedge_side: str,
        logger
    ):
        self.close_result_calculator = close_result_calculator
        self.hedge_side = hedge_side
        self.logger = logger

    def _get_profitable_levels(
        self,
        levels: list[StackElem],
        current_price: float,
    ) -> list[StackElem]:
        if self.hedge_side == "Sell":
            return [
                level for level in levels
                if level.price > current_price
            ]

        if self.hedge_side == "Buy":
            return [
                level for level in levels
                if level.price < current_price
            ]

        raise ValueError(f"Unsupported side: {self.hedge_side}")

    def _is_close_result_acceptable(
        self,
        close_result: float,
    ) -> bool:
        return close_result >= 0

    def find_alternative_profitable_level(
        self,
        losing_level: StackElem,
        sorted_levels: list[StackElem],
        cur_price: float,
    ) -> StackElem | None:
        # Получаем прибыльные уровни
        profitable_levels = self._get_profitable_levels(
            sorted_levels,
            cur_price,
        )

        # self.logger.info(
        #     f"[OPT] ALT SEARCH | Losing level: {losing_level.price:.6f}/{losing_level.qty} | "
        #     f"Cur price: {cur_price:.6f} | Candidates count: {len(profitable_levels)}"
        # )

        # Проходим по прибыльным уровням и ищем тот, который закроет losing_level в прибыль
        for profit_level in profitable_levels:
            # Вычисляем netto pnl при закрытии пары
            close_pair_netto_pnl = self.close_result_calculator.calc_netto_pnl(
                losing_level,
                profit_level,
                cur_price,
            )

            is_acceptable = self._is_close_result_acceptable(close_pair_netto_pnl)

            # self.logger.info(
            #     f"[OPT] ALT CHECK | Profit candidate: {profit_level.price:.6f}/{profit_level.qty} | "
            #     f"Netto PnL: {close_pair_netto_pnl:.8f} | Acceptable: {is_acceptable}"
            # )

            # Если результат закрытия устраивает -> возвращаем найденный прибыльный уровень
            if is_acceptable:
                # self.logger.info(
                #     f"[OPT] ALT SELECTED | Chosen profit level: {profit_level.price:.6f}/{profit_level.qty}"
                # )
                return profit_level

        # self.logger.info("[OPT] ALT SEARCH | No acceptable profit level found.")
        return None