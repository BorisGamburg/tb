class HaAnalyzer:
    """
    Чистая логика анализа свечей Heikin Ashi.
    """

    @staticmethod
    def _require_fields(data: dict, *fields):
        missing = [f for f in fields if data.get(f) is None]
        if missing:
            raise ValueError(f"HaAnalyzer: missing fields {missing}")

    @staticmethod
    def is_reversal(side: str, data: dict) -> bool:
        if side == "Sell":
            return HaAnalyzer.is_reversal_up(data)
        return HaAnalyzer.is_reversal_down(data)

    @staticmethod
    def is_reversal_up(data: dict) -> bool:
        """
        Выход из SELL
        """
        HaAnalyzer._require_fields(data, "curr_ha", "prev_ha", "last_price")

        curr = data["curr_ha"]   # последняя закрытая
        prev = data["prev_ha"]   # предыдущая
        price = data["last_price"]

        prev_red = prev["HA_close"] < prev["HA_open"]
        curr_green = curr["HA_close"] > curr["HA_open"]
        curr_red = curr["HA_close"] < curr["HA_open"]

        # 1. подтверждённый разворот
        if prev_red and curr_green:
            return True

        # 2. ранний выход (пробой open последней закрытой)
        if curr_red and price > curr["HA_open"]:
            return True

        return False

    @staticmethod
    def is_reversal_down(data: dict) -> bool:
        """
        Выход из BUY
        """
        HaAnalyzer._require_fields(data, "curr_ha", "prev_ha", "last_price")

        curr = data["curr_ha"]
        prev = data["prev_ha"]
        price = data["last_price"]

        prev_green = prev["HA_close"] > prev["HA_open"]
        curr_red = curr["HA_close"] < curr["HA_open"]
        curr_green = curr["HA_close"] > curr["HA_open"]

        # 1. подтверждённый разворот
        if prev_green and curr_red:
            return True

        # 2. ранний выход
        if curr_green and price < curr["HA_open"]:
            return True

        return False