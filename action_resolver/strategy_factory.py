import yaml
from pathlib import Path
from action_processor.state.state import State
from common.trading_info import TradingInfo


class StrategyFactory:
    @staticmethod
    def _read_yaml_file(file_path: Path) -> dict:
        """Вспомогательный метод для чтения и парсинга YAML-файла."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.load(f, Loader=yaml.SafeLoader) or {}    

    @staticmethod
    def _load_trading_info(
        symbol: str,
        proxy_driver,
    ) -> TradingInfo:

        symbol_info = proxy_driver.execute(
            "get_symbol_info",
            symbol=symbol,
        )

        if not symbol_info or symbol_info.get("retCode") != 0:
            msg = symbol_info.get("retMsg") if symbol_info else "Пустой ответ"
            raise Exception(
                f"Ошибка получения информации об инструменте "
                f"{symbol}: {msg}"
            )

        filters = symbol_info["result"]["list"][0]["lotSizeFilter"]

        fee_data = proxy_driver.execute(
            "get_fee_rates",
            symbol=symbol,
        )

        return TradingInfo(
            symbol=symbol,
            qty_step=float(filters["qtyStep"]),
            min_qty=float(filters["minOrderQty"]),
            fee_taker=float(fee_data["taker"]),
        )
    @classmethod
    def initialize(
        cls,
        config_file: Path,
        app_ctx,
    ):
        """
        ЕДИНАЯ ТОЧКА ВХОДА: Загружает файл, валидирует, создает State и Стратегию.
        Всё происходит в ОДНОЙ функции и в ОДНОМ месте.
        """
        # 1. Читаем сырой YAML
        parsed_data = cls._read_yaml_file(config_file)

        strategy_name = parsed_data.get("strategy")

        # =========================================================
        # --- СТРАТЕГИЯ 1: grid_mtf ---
        # =========================================================
        if strategy_name == "grid_mtf":
            from action_resolver.grid_mtf_strategy.grid_mtf_schema import GridMTFSchema
            from action_resolver.grid_mtf_strategy.grid_mtf_map_mng import GridMTFMapMng
            from action_resolver.grid_mtf_strategy.grid_mtf_strategy import GridMTFStrategy

            # Валидируем данные через Pydantic
            config_data = GridMTFSchema.model_validate(parsed_data)

            trading_info = cls._load_trading_info(
                symbol=config_data.symbol,
                proxy_driver=app_ctx.proxy_driver,
            )

            # Создаем State
            state_store = State(config_file=config_file, config_data=config_data, logger=app_ctx.logger)

            # Создаем менеджер карты и передаем его в State
            map_mng = GridMTFMapMng(
                symbol=config_data.symbol,
                side=config_data.side,
                templates=config_data.templates,
                stack=config_data.stack,
                proxy_driver=app_ctx.proxy_driver,
                logger=app_ctx.logger,
            )
            state_store.map_mng = map_mng

            # Создаем объект стратегии
            strategy = GridMTFStrategy(
                state_store=state_store,
                map_mng=map_mng,
                app_ctx=app_ctx,
                trading_info=trading_info,
            )

            return state_store, strategy

        # =========================================================
        # --- СТРАТЕГИЯ 2: hedge_2 ---
        # =========================================================
        if strategy_name == "hedge_2":
            from action_resolver.hedge_2_strategy.hedge_2_schema import Hedge2Schema
            from action_resolver.hedge_2_strategy.hedge_2_strategy import Hedge2Strategy

            # Валидируем данные через Pydantic
            config_data = Hedge2Schema.model_validate(parsed_data)

            trading_info = cls._load_trading_info(
                symbol=config_data.symbol,
                proxy_driver=app_ctx.proxy_driver,
            )

            # Создаем State
            state_store = State(config_file=config_file, config_data=config_data, logger=app_ctx.logger)

            # Создаем объект стратегии
            strategy = Hedge2Strategy(
                state_store=state_store,
                app_ctx=app_ctx,
                trading_info=trading_info,
            )

            return state_store, strategy

        raise ValueError(f"Неизвестная стратегия: {strategy_name}")

