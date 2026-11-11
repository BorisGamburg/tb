"""Добавляет стратегию hedge_3 в action_resolver/strategy_factory.py.

Блок вставляется перед баннером стратегии pyramid. Скрипт безопасен для
повторного запуска: если hedge_3 уже есть, файл не меняется.
"""
import shutil
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "action_resolver/strategy_factory.py")
text = path.read_text(encoding="utf-8")

if 'strategy_name == "hedge_3"' in text:
    print("hedge_3 уже есть, ничего не делаю")
    raise SystemExit(0)

BLOCK = '''        # =========================================================
        # --- СТРАТЕГИЯ: hedge_3 ---
        # =========================================================
        if strategy_name == "hedge_3":
            from action_resolver.hedge_3_strategy.hedge_3_schema import Hedge3Schema
            from action_resolver.hedge_3_strategy.hedge_3_strategy import Hedge3Strategy

            # Валидируем данные через Pydantic
            config_data = Hedge3Schema.model_validate(parsed_data)

            trading_info = cls._load_trading_info(
                symbol=config_data.symbol,
                proxy_driver=app_ctx.proxy_driver,
            )

            # Создаем State
            state_store = State(config_file=config_file, config_data=config_data, logger=app_ctx.logger)

            # Создаем объект стратегии
            strategy = Hedge3Strategy(
                state_store=state_store,
                app_ctx=app_ctx,
                trading_info=trading_info,
            )

            return state_store, strategy, trading_info

'''

lines = text.splitlines(keepends=True)
marker = next(
    (i for i, l in enumerate(lines) if "СТРАТЕГИЯ 3: pyramid" in l), None
)
if marker is None or not lines[marker - 1].lstrip().startswith("# ===="):
    print("Не нашёл место вставки (баннер 'СТРАТЕГИЯ 3: pyramid'). Файл не изменён.")
    raise SystemExit(1)

shutil.copy(path, str(path) + ".bak")
lines.insert(marker - 1, BLOCK)
path.write_text("".join(lines), encoding="utf-8")
print("hedge_3 добавлена, резервная копия:", str(path) + ".bak")
