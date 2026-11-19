from math import isfinite


class PyramidModeResolver:
    """Determine the current Pyramid 2 operating mode."""

    EMPTY_MODE = "EMPTY_MODE"
    PROFIT_MODE = "PROFIT_MODE"
    RECOVERY_MODE = "RECOVERY_MODE"

    @staticmethod
    def resolve(
        side: str,
        current_price: float,
        stack_mng,
        fee_taker: float,
    ) -> str:
        """Resolve the mode using the current price and calculated stack BE."""

        if side not in ("Buy", "Sell"):
            raise ValueError(f"Unsupported position side: {side}")

        # Если стек пустой выходим с EMPTY_MODE
        if stack_mng.is_empty():
            return PyramidModeResolver.EMPTY_MODE

        # Получаем безубыток стека
        stack_be = stack_mng.calculate_break_even_price(
            side,
            fee_taker,
        )

        if stack_be is None:
            raise RuntimeError("Cannot calculate BE for non-empty stack")

        if not isfinite(current_price) or current_price <= 0:
            raise ValueError(f"Invalid current price: {current_price}")

        # Определяем режим
        if side == "Buy":
            if current_price > stack_be:
                return PyramidModeResolver.PROFIT_MODE
            return PyramidModeResolver.RECOVERY_MODE

        if current_price < stack_be:
            return PyramidModeResolver.PROFIT_MODE

        return PyramidModeResolver.RECOVERY_MODE