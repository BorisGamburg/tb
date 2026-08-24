import logging
from proxy_server.proxy_driver import ProxyDriver


class GridMTFMapMng:

    def __init__(
        self,
        symbol: str,
        side: str,
        templates,
        stack,
        proxy_driver: ProxyDriver,
        logger: logging.Logger
    ):
        self.symbol = symbol
        self.side = side
        self.stack = stack
        self.logger = logger
        self.proxy_driver = proxy_driver

        self.templates = templates

        # сортируем templates
        self.templates_sorted = sorted(
            templates.items(),
            key=lambda x: x[0]
        )        

    def get_template_by_level(self, level: int):

        if not self.templates_sorted:
            raise RuntimeError("templates_sorted is empty")

        if level >= len(self.templates_sorted):
            raise RuntimeError(
                f"Level {level} exceeds templates ({len(self.templates_sorted)})"
            )

        _, tpl = self.templates_sorted[level]

        return tpl 

    def get_tf_for_level(self, level: int) -> str:
        tpl = self.get_template_by_level(level)
        return tpl.tf_filter 

    def get_cur_map_elem(self):

        entries = self.stack.entries
        level = len(entries)

        return self.get_template_by_level(level)          