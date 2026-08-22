class BBExtremeSignal:

    def __init__(self, symbol, side, proxy_driver):
        self.symbol = symbol
        self.side = side
        self.proxy_driver = proxy_driver

    def check_avdo(self, map_elem):

        data = self.proxy_driver.get_data(
            symbol=self.symbol,
            tf=str(map_elem.tf)
        )

        price = data["last_price"]
        bb_high = data["bb_high"]
        bb_low = data["bb_low"]
        bb_mid = data["bb_mid"]
        bbw = bb_high - bb_low

        if self.side == "Sell":
            extreme = price >= (bb_mid + bbw)
        else:
            extreme = price <= (bb_mid - bbw)

        if extreme:
            return True, f"bb extreme {price}"

        return False, "no extreme"
    
    def check_prta(self, map_elem):
        # Используем таймфрейм для тейк-профита 
        data = self.proxy_driver.get_data(
            symbol=self.symbol,
            tf=str(map_elem.tf)
        )

        price = data["last_price"]
        bb_high = data["bb_high"]
        bb_low = data["bb_low"]
        bb_mid = data["bb_mid"]
        bbw = bb_high - bb_low

        if self.side == "Sell":
            # Экстрим тейк для Sell: цена упала ниже средней на всю ширину BB
            extreme = price <= (bb_mid - bbw)
        else:
            # Экстрим тейк для Buy: цена выросла выше средней на всю ширину BB
            extreme = price >= (bb_mid + bbw)

        if extreme:
            return True, f"bb extreme prta {price}"

        return False, "no extreme"    