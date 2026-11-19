from action_processor.action import Action, ActionCommand
from action_resolver.resolve_result import ResolveResult
from utils.utils import get_inverse_side
from action_resolver.pyramid_2_strategy.pyr_close_processor import (
    PyrCloseProcessor,
)
from action_resolver.pyramid_2_strategy.pyr_rearm import PyrRearm
from action_resolver.pyramid_2_strategy.pyr_ha_breakout_opener import (
    PyrHaBreakoutOpener,
)
from common.level_distance_checker import is_level_distance_allowed


class PyrProfitMode:

    def __init__(
        self,
        state_store,
        app_ctx,
        trading_info,
        action_service,
        open_checker,
        close_processor: PyrCloseProcessor,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.trading_info = trading_info
        self.action_service = action_service
        self.open_checker = open_checker
        self.close_processor = close_processor

        self.rearm = PyrRearm(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            open_checker=open_checker,
        )

        # Используем тот же HA Breakout, который уже создан в EntryChecker.
        self.ha_opener = PyrHaBreakoutOpener(
            state_store=state_store,
            app_ctx=app_ctx,
            action_service=action_service,
            ha_signal=open_checker.ha_signal,
        )

    def resolve(self) -> ResolveResult:
        close_result = self._process_extension_close()

        if close_result is not None:
            return close_result

        return self._process_ha_breakout()

    def _get_extension_levels(self):
        data = self.state_store.data
        entries = data.stack.entries

        if not entries:
            return []

        if data.side == "Buy":
            base_level = min(entries, key=lambda level: level.price)
        else:
            base_level = max(entries, key=lambda level: level.price)

        return [
            level
            for level in entries
            if level is not base_level
        ]

    def _process_extension_close(self) -> ResolveResult | None:
        data = self.state_store.data
        extensions = self._get_extension_levels()

        if not extensions:
            return None

        # Получаем Ask/Bid 
        ticker = self.app_ctx.proxy_driver.get_ticker(data.symbol)
        bid = float(ticker["bid"])
        ask = float(ticker["ask"])

        step_ratio = self.open_checker.step_ratio

        close_level = None

        # Ищем уровеня для закрытия
        close_level = self.find_close_level(data, extensions, bid, ask, step_ratio)
        if close_level is None:
            return None

        # Уровеень для закрытия найден, формируем команду на закрытие.
        close_command = ActionCommand(
            action=Action.CLOSE,
            symbol=data.symbol,
            side=get_inverse_side(data.side),
            qty=close_level.qty,
            levels=[close_level],
            reason="PYRAMID_PROFIT_CLOSE",
        )

        # Отправляем команду на закрытие через CloseProcessor.
        close_result = self.close_processor.execute_profit_close(
            close_command
        )

        exec_result = close_result.execution_result

        # Проверяем результат исполнения команды.
        if not exec_result.executed:
            return ResolveResult(
                executed=False,
                status="PROFIT CLOSE: NOT FILLED",
            )

        # Проверяем закрылся уровень полностью или частично.
        if not close_result.fully_closed:
            # Частичное закрытие уровня -> rearm не выполняем
            return ResolveResult(
                executed=True,
                status=(
                    f"PROFIT CLOSE: PARTIAL "
                    f"| price={close_level.price}"
                ),
            )

        # Полное закрытие уровня -> пробуем выполнить rearm.
        rearm_status = self.rearm.try_rearm()

        # Возвращаем результат закрытия уровня с информацией о rearm.
        return ResolveResult(
            executed=True,
            status=(
                f"PROFIT CLOSE: FULL "
                f"| price={close_level.price} "
                f"| {rearm_status}"
            ),
        )

    def find_close_level(self, data, extensions, bid, ask, step_ratio):
        for level in extensions:
            if data.side == "Buy":
                close_price_reached = (
                    bid >= level.price * (1 + step_ratio)
                )
            else:
                close_price_reached = (
                    ask <= level.price * (1 - step_ratio)
                )

            if close_price_reached:
                return level

        return None

    def _process_ha_breakout(self) -> ResolveResult:
        data = self.state_store.data

        # Проверяем HA Signal
        if not self.ha_opener.has_signal():
            # HA Signal отсутствует -> выходим
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: NO SIGNAL",
            )

        # Получаем qty
        qty = self.open_checker.get_qty()
        if qty <= 0:
            # qty <= 0 -> выходим
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: SKIPPED (QTY = 0)",
            )

        # Стек пустой -> открываем Base по сигналу,
        # без проверки дистанции и буфера BE.
        if not data.stack.entries:
            return self.ha_opener.open(
                qty, "BASE (EMPTY STACK)", is_base=True
            )

        # Стек не пуст: проверяем дистанцию до каждого уровня
        cur_price = float(
            self.app_ctx.proxy_driver.get_last_price(data.symbol)
        )
        if not is_level_distance_allowed(
            cur_price=cur_price,
            entries=data.stack.entries,
            hedge_step_ratio=self.open_checker.step_ratio,
        ):
            # Дистанция не прошла -> выходим
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: SKIPPED (DISTANCE)",
            )

        # Дистанция ОК: открываем Extension, только если хватает буфера
        buffer_ok, buffer_info = self._check_buffer_after_open(qty)
        if not buffer_ok:
            # Проверка буфера не прошла -> выходим
            return ResolveResult(
                executed=False,
                status=f"HA BREAKOUT: SKIPPED | {buffer_info}",
            )

        # Открываем уровень
        return self.ha_opener.open(qty, buffer_info)


    def _check_buffer_after_open(self, qty: float) -> tuple[bool, str]:
        """Хватит ли буфера до BE, если открыть новый уровень сейчас.

        Возвращает (достаточно ли, описание для статуса).
        """
        data = self.state_store.data

        # Текущая цена активной стороны спреда
        active_price = self.ha_opener.get_active_price()

        # Какой будет буфер, если открыть уровень сейчас
        buffer_after_open_pct = self._calc_buffer_after_open(active_price, qty)

        # Минимальный буфер из конфига
        min_buffer_pct = float(data.min_be_buffer_pct)

        if buffer_after_open_pct < min_buffer_pct:
            return False, (
                f"BUFFER {buffer_after_open_pct:.4f}% "
                f"< {min_buffer_pct:.4f}%"
            )

        return True, (
            f"BUFFER {buffer_after_open_pct:.4f}% "
            f">= {min_buffer_pct:.4f}%"
        )    

    def _calc_buffer_after_open(self, active_price: float, qty: float) -> float:
        """Буфер (в %) между ценой и новым BE стека после модельного открытия."""
        data = self.state_store.data
        fee_taker = self.trading_info.fee_taker

        # Моделируем новый уровень, не меняя реальный стек.
        # Создаем стек для моделирования
        simulated_stack = self.state_store.stack_mng.clone()

        # Добавляем в simulated_stack новый уровень
        simulated_stack.push(
            price=active_price,
            qty=qty,
            initial_qty=qty,
            fee=active_price * qty * fee_taker,
        )

        # Рассчитываем безубыток simulated_stack
        simulated_stack_be = simulated_stack.calculate_break_even_price(
            side=data.side,
            fee_taker=fee_taker,
        )
        if simulated_stack_be is None:
            # Не смогли рассчитать безубыток -> исключение
            raise RuntimeError(
                "Cannot calculate BE after simulated HA Breakout entry"
            )

        # Безубыток рассчитан
        # Рассчитываем буфер simulated_stack
        if data.side == "Buy":
            buffer_pct = (active_price - simulated_stack_be) / active_price * 100
        else:
            buffer_pct = (simulated_stack_be - active_price) / active_price * 100

        # Буфер рассчитан -> выходим
        return buffer_pct