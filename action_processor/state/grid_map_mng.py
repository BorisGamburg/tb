import logging
from prog.metrics.pos_metrics import PositionMetrics
from prog.proxy_server.proxy_driver import ProxyDriver
from prog.action_processor.state.map_elem import MapElem

class GridMapMng:
    """
    Управляет выбором текущего элемента карты стратегий (MapElem) 
    на основе текущего размера стека ордеров (StackManager).
    """
    def __init__(self, 
        symbol: str,
        templates, 
        proxy_driver: ProxyDriver,
        logger: logging.Logger,
        max_position_pct: float,
        side_main: str
    ):
        self.templates = templates 
        self.symbol = symbol
        self.logger = logger
        self.max_position_pct = max_position_pct
        self.side_main = side_main

        self.pos_metrics  = PositionMetrics(proxy_driver, side_main=side_main)

    def select_template(self) -> str:
        net_pos_pct = self.pos_metrics.net_pos_pct(self.symbol)

        if not self.max_position_pct or self.max_position_pct <= 0:
            raise ValueError("max_position_pct must be a positive number")

        ratio = net_pos_pct / self.max_position_pct
        ratio = max(0.0, min(1.0, ratio))  # clamp

        if ratio < 0.15:
            return "ultra_fast"
        elif ratio < 0.35:
            return "fast"
        elif ratio < 0.60:
            return "medium"
        elif ratio < 0.85:
            return "slow"
        else:
            return "survival"
        
    def get_cur_map_elem(self) -> MapElem:
            template_name = self.select_template()
            return self.templates[template_name]        
        
        