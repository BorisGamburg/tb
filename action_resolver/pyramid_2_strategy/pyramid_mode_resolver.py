from math import isfinite


class PyramidModeResolver:
    """Determine the current Pyramid 2 operating mode."""

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

        stack_be = stack_mng.calculate_break_even_price(
            side,
            fee_taker,
        )

        if stack_be is None:
            return PyramidModeResolver.PROFIT_MODE

        if not isfinite(current_price) or current_price <= 0:
            raise ValueError(f"Invalid current price: {current_price}")

        if side == "Buy":
            if current_price > stack_be:
                return PyramidModeResolver.PROFIT_MODE
            return PyramidModeResolver.RECOVERY_MODE

        if current_price < stack_be:
            return PyramidModeResolver.PROFIT_MODE

        return PyramidModeResolver.RECOVERY_MODE
